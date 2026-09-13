/**
 * Deterministic mission-time evaluator — the piece CLAUDE.md rule 14 exists
 * for. Every exported function here is pure: same inputs always produce the
 * same output, with no reliance on wall-clock time, setInterval or
 * requestAnimationFrame. The React layer (ScrubBar/PlaybackControls) owns
 * the *only* place frame timing exists in this feature; it just advances a
 * `scenarioTimeSeconds` number and calls these functions with it.
 *
 * Per-template coverage (see docs/architecture/implementation-plan.md's M3
 * section for the full rationale):
 *   - waypoint_transit, scripted_track: full arc-length interpolation.
 *   - orbit: real angular motion around waypoint[0], radius from
 *     template_parameters.radius_m (default 100m if absent — documented
 *     assumption, see domain/geojson.ts:orbitCenterAndRadius). Loops
 *     indefinitely.
 *   - racetrack, perimeter_patrol: closed-loop arc-length interpolation
 *     over the authored waypoints, looping indefinitely. A "real" racetrack
 *     (straight legs + turn-radius arcs) needs template_parameters keys the
 *     backend schema doesn't validate/require yet — deferred.
 *   - grid_search: ordered arc-length interpolation over the authored
 *     waypoints (operator authors the actual grid points); no procedural
 *     grid generation from a bounding box this milestone.
 *   - loiter_then_depart: no special code — the last waypoint's
 *     hold_seconds already models the loiter.
 *   - swarm_staggered_arrival: no special trajectory code — staggering is
 *     each mission's own start_policy/start_time_offset, already handled.
 */

import { durationToSeconds } from "./duration";
import {
  bearingDegrees,
  haversineDistanceMeters,
  lerp,
  lerpPosition,
  pointOnCircle,
  orbitCenterAndRadius,
} from "./geojson";
import type {
  AltitudeReference,
  DroneMission,
  GeoPosition2D,
  MissionRelativeTimelineEvent,
  TimelineEvent,
  Trajectory,
  Waypoint,
} from "./types";

export type MissionPhase = "before_start" | "en_route" | "holding" | "completed";

export interface MissionState {
  positionLonLat: GeoPosition2D;
  altitudeM: number;
  altitudeReference: AltitudeReference;
  headingDeg: number;
  speedMps: number;
  phase: MissionPhase;
  completionFraction: number;
  activeSegmentIndex: number | null;
}

const LOOPING_TEMPLATES = new Set(["orbit", "racetrack", "perimeter_patrol"]);

export function isLoopingTemplate(template: Trajectory["template"]): boolean {
  return LOOPING_TEMPLATES.has(template);
}

/** Mission start, in scenario-time seconds. Infinity = never auto-starts. */
export function evaluateMissionStartSeconds(mission: DroneMission): number {
  switch (mission.start_policy) {
    case "at_scenario_start":
      return 0;
    case "at_time_offset":
      // Backend validates start_time_offset is present for this policy.
      return durationToSeconds(mission.start_time_offset as string);
    case "on_event":
    case "manual":
      // Not evaluable from scenario time alone in this milestone — the
      // mission never starts in the M3 playback preview. Documented TODO:
      // needs an orchestration/timeline-execution milestone to resolve.
      return Infinity;
  }
}

function legSpeedMps(trajectory: Trajectory, fromWaypoint: Waypoint): number {
  return fromWaypoint.speed_mps ?? trajectory.default_speed_mps;
}

interface Leg {
  fromIndex: number;
  toIndex: number;
  holdStart: number;
  holdEnd: number;
  legEnd: number;
}

interface LegSchedule {
  ordered: Waypoint[];
  legs: Leg[];
  looping: boolean;
  /** Loop period (looping templates) or total one-shot duration incl. final hold. */
  totalDuration: number;
}

function buildLegSchedule(trajectory: Trajectory): LegSchedule {
  const ordered = [...trajectory.waypoints].sort((a, b) => a.sequence_index - b.sequence_index);
  const looping = isLoopingTemplate(trajectory.template) && trajectory.template !== "orbit";
  const legCount = looping ? ordered.length : ordered.length - 1;

  const legs: Leg[] = [];
  let cursor = 0;
  for (let i = 0; i < legCount; i++) {
    const fromIndex = i;
    const toIndex = looping ? (i + 1) % ordered.length : i + 1;
    const from = ordered[fromIndex];
    const to = ordered[toIndex];
    const holdStart = cursor;
    const holdEnd = holdStart + from.hold_seconds;
    const distanceM = haversineDistanceMeters(from.position.coordinates, to.position.coordinates);
    const transitS = distanceM / legSpeedMps(trajectory, from);
    const legEnd = holdEnd + transitS;
    legs.push({ fromIndex, toIndex, holdStart, holdEnd, legEnd });
    cursor = legEnd;
  }

  let totalDuration = cursor;
  if (!looping && ordered.length > 0) {
    // One-shot: the final waypoint's hold_seconds is a dwell before
    // "completed" (this is what makes loiter_then_depart work).
    totalDuration += ordered[ordered.length - 1].hold_seconds;
  }

  return { ordered, legs, looping, totalDuration };
}

function evaluateOrbitState(trajectory: Trajectory, missionTimeSeconds: number): MissionState {
  const [center, radiusM] = orbitCenterAndRadius(trajectory);
  const speedMps = trajectory.default_speed_mps;
  const angularVelocityDegPerS = radiusM > 0 ? (speedMps / radiusM) * (180 / Math.PI) : 0;
  const periodS = angularVelocityDegPerS > 0 ? 360 / angularVelocityDegPerS : Infinity;
  const angleDeg = (missionTimeSeconds * angularVelocityDegPerS) % 360;
  const position = pointOnCircle(center, radiusM, angleDeg);
  // Heading = tangent direction of travel (angle + 90deg in local frame).
  const headingPoint = pointOnCircle(center, radiusM, angleDeg + 1);
  const referenceWaypoint = trajectory.waypoints[0];

  return {
    positionLonLat: position,
    altitudeM: referenceWaypoint.altitude_m,
    altitudeReference: referenceWaypoint.altitude_reference,
    headingDeg: bearingDegrees(position, headingPoint),
    speedMps,
    phase: "en_route",
    completionFraction: Number.isFinite(periodS) ? (missionTimeSeconds % periodS) / periodS : 0,
    activeSegmentIndex: null,
  };
}

/** Position/velocity/altitude/heading/phase at an arbitrary scenario time. */
export function evaluateMissionState(
  mission: DroneMission,
  scenarioTimeSeconds: number,
): MissionState {
  const trajectory = mission.trajectory;
  const startSeconds = evaluateMissionStartSeconds(mission);
  const first = [...trajectory.waypoints].sort((a, b) => a.sequence_index - b.sequence_index)[0];

  if (scenarioTimeSeconds < startSeconds) {
    return {
      positionLonLat: first.position.coordinates as GeoPosition2D,
      altitudeM: first.altitude_m,
      altitudeReference: first.altitude_reference,
      headingDeg: 0,
      speedMps: 0,
      phase: "before_start",
      completionFraction: 0,
      activeSegmentIndex: null,
    };
  }

  const missionTimeSeconds = scenarioTimeSeconds - startSeconds;

  if (trajectory.template === "orbit") {
    return evaluateOrbitState(trajectory, missionTimeSeconds);
  }

  const schedule = buildLegSchedule(trajectory);
  const t = schedule.looping ? missionTimeSeconds % schedule.totalDuration : missionTimeSeconds;

  if (!schedule.looping && t >= schedule.totalDuration) {
    const last = schedule.ordered[schedule.ordered.length - 1];
    return {
      positionLonLat: last.position.coordinates as GeoPosition2D,
      altitudeM: last.altitude_m,
      altitudeReference: last.altitude_reference,
      headingDeg: 0,
      speedMps: 0,
      phase: "completed",
      completionFraction: 1,
      activeSegmentIndex: null,
    };
  }

  for (const leg of schedule.legs) {
    if (t < leg.holdEnd) {
      const from = schedule.ordered[leg.fromIndex];
      const to = schedule.ordered[leg.toIndex];
      return {
        positionLonLat: from.position.coordinates as GeoPosition2D,
        altitudeM: from.altitude_m,
        altitudeReference: from.altitude_reference,
        headingDeg: bearingDegrees(from.position.coordinates, to.position.coordinates),
        speedMps: 0,
        phase: "holding",
        completionFraction: schedule.looping
          ? t / schedule.totalDuration
          : t / schedule.totalDuration,
        activeSegmentIndex: leg.fromIndex,
      };
    }
    if (t < leg.legEnd) {
      const from = schedule.ordered[leg.fromIndex];
      const to = schedule.ordered[leg.toIndex];
      const fraction = (t - leg.holdEnd) / (leg.legEnd - leg.holdEnd);
      return {
        positionLonLat: lerpPosition(from.position.coordinates, to.position.coordinates, fraction),
        altitudeM: lerp(from.altitude_m, to.altitude_m, fraction),
        altitudeReference: to.altitude_reference,
        headingDeg: bearingDegrees(from.position.coordinates, to.position.coordinates),
        speedMps: legSpeedMps(trajectory, from),
        phase: "en_route",
        completionFraction: t / schedule.totalDuration,
        activeSegmentIndex: leg.fromIndex,
      };
    }
  }

  // One-shot final hold, past the last leg's transit but before totalDuration.
  const last = schedule.ordered[schedule.ordered.length - 1];
  return {
    positionLonLat: last.position.coordinates as GeoPosition2D,
    altitudeM: last.altitude_m,
    altitudeReference: last.altitude_reference,
    headingDeg: 0,
    speedMps: 0,
    phase: "holding",
    completionFraction: t / schedule.totalDuration,
    activeSegmentIndex: schedule.ordered.length - 1,
  };
}

/** Multi-drone convenience — a trivial map, kept here so it's unit-testable without React. */
export function evaluateScenarioState(
  missions: DroneMission[],
  scenarioTimeSeconds: number,
): Map<string, MissionState> {
  return new Map(missions.map((m) => [m.id, evaluateMissionState(m, scenarioTimeSeconds)]));
}

/** Scenario-time seconds at which a waypoint is first reached (non-looping schedules only). */
export function arrivalSecondsAtWaypoint(
  mission: DroneMission,
  sequenceIndex: number,
): number | null {
  const trajectory = mission.trajectory;
  if (trajectory.template === "orbit") return null; // not well-defined for continuous motion

  const startSeconds = evaluateMissionStartSeconds(mission);
  if (!Number.isFinite(startSeconds)) return null;

  const schedule = buildLegSchedule(trajectory);
  const targetIdx = schedule.ordered.findIndex((w) => w.sequence_index === sequenceIndex);
  if (targetIdx === -1) return null;
  if (targetIdx === 0) return startSeconds + 0;

  const leg = schedule.legs.find((l) => l.toIndex === targetIdx);
  return leg ? startSeconds + leg.legEnd : null;
}

/**
 * Scenario-time seconds a timeline event fires, or null if it isn't
 * evaluable from scenario time alone (manual_gated/external/safety events,
 * and mission_relative area_entry/phase_completion anchors — documented
 * TODOs pending later milestones).
 */
export function evaluateTimelineEventFireSeconds(
  event: TimelineEvent,
  missions: DroneMission[],
): number | null {
  if (event.kind === "absolute") {
    return durationToSeconds(event.scenario_time_offset);
  }
  if (event.kind === "mission_relative") {
    return evaluateMissionRelativeFireSeconds(event, missions);
  }
  return null;
}

function evaluateMissionRelativeFireSeconds(
  event: MissionRelativeTimelineEvent,
  missions: DroneMission[],
): number | null {
  const mission = missions.find((m) => m.id === event.mission_id);
  if (!mission) return null;
  const offsetSeconds = durationToSeconds(event.offset);
  const startSeconds = evaluateMissionStartSeconds(mission);
  if (!Number.isFinite(startSeconds)) return null;

  if (event.anchor === "mission_start") {
    return startSeconds + offsetSeconds;
  }
  if (event.anchor === "waypoint") {
    if (event.waypoint_sequence_index === null) return null;
    const arrival = arrivalSecondsAtWaypoint(mission, event.waypoint_sequence_index);
    return arrival === null ? null : arrival + offsetSeconds;
  }
  // area_entry, phase_completion: not evaluable from scenario time alone.
  return null;
}

/** Upper bound for the timeline scrub range — max over all missions. */
export function scenarioDurationSeconds(missions: DroneMission[]): number {
  let max = 0;
  for (const mission of missions) {
    const startSeconds = evaluateMissionStartSeconds(mission);
    if (!Number.isFinite(startSeconds)) continue;
    if (mission.trajectory.template === "orbit") {
      const [, radiusM] = orbitCenterAndRadius(mission.trajectory);
      const angularVelocity =
        radiusM > 0 ? (mission.trajectory.default_speed_mps / radiusM) * (180 / Math.PI) : 0;
      const periodS = angularVelocity > 0 ? 360 / angularVelocity : 0;
      max = Math.max(max, startSeconds + periodS);
      continue;
    }
    const schedule = buildLegSchedule(mission.trajectory);
    const missionSpan = schedule.looping ? schedule.totalDuration : schedule.totalDuration;
    max = Math.max(max, startSeconds + missionSpan);
  }
  return max;
}
