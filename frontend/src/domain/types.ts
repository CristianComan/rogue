/**
 * Hand-written domain types mirroring backend/rogue/domain/. These are what
 * components, the mission evaluator and forms operate on — the API client
 * layer (src/api/scenarios.ts) is the only place that converts between
 * these and the raw wire format (parsing ISO8601 durations, etc.).
 *
 * All UUIDs are strings, all timestamps are ISO8601 UTC strings, all
 * durations are ISO8601 duration strings (e.g. "PT5S") — the same
 * convention Pydantic's model_dump(mode="json") produces.
 */

// ---------------------------------------------------------------- geojson

export type GeoPosition2D = [lon: number, lat: number];
export type GeoPosition3D = [lon: number, lat: number, altitudeM: number];
export type GeoPosition = GeoPosition2D | GeoPosition3D;

// mirrors backend/rogue/domain/common.py:GeoPoint
export interface GeoPoint {
  type: "Point";
  coordinates: GeoPosition;
}

// mirrors backend/rogue/domain/common.py:GeoLineString
export interface GeoLineString {
  type: "LineString";
  coordinates: GeoPosition[];
}

// mirrors backend/rogue/domain/common.py:GeoPolygon
export interface GeoPolygon {
  type: "Polygon";
  coordinates: GeoPosition[][];
}

// ------------------------------------------------------------------ zone

// mirrors backend/rogue/domain/scenario.py:ZoneType
export type ZoneType = "operational_area" | "no_transmit" | "no_fly" | "restricted" | "custom";

// mirrors backend/rogue/domain/scenario.py:Zone
export interface Zone {
  id: string;
  zone_type: ZoneType;
  polygon: GeoPolygon;
  label: string | null;
  notes: string | null;
}

// --------------------------------------------------------------- mission

// mirrors backend/rogue/domain/mission.py:PlatformCategory
export type PlatformCategory = "multirotor" | "fixed_wing" | "vtol" | "other";

// mirrors backend/rogue/domain/mission.py:Platform
export interface Platform {
  name: string;
  category: PlatformCategory;
  max_speed_mps: number;
  max_climb_rate_mps: number | null;
  notes: string | null;
}

// mirrors backend/rogue/domain/mission.py:MissionTemplate
export type MissionTemplate =
  | "waypoint_transit"
  | "orbit"
  | "racetrack"
  | "grid_search"
  | "perimeter_patrol"
  | "loiter_then_depart"
  | "swarm_staggered_arrival"
  | "scripted_track";

// mirrors backend/rogue/domain/mission.py:AltitudeReference
export type AltitudeReference = "agl" | "msl";

// mirrors backend/rogue/domain/mission.py:Waypoint
export interface Waypoint {
  sequence_index: number;
  position: GeoPoint;
  altitude_m: number;
  altitude_reference: AltitudeReference;
  speed_mps: number | null;
  heading_deg: number | null;
  hold_seconds: number;
}

// mirrors backend/rogue/domain/mission.py:Trajectory
export interface Trajectory {
  template: MissionTemplate;
  waypoints: Waypoint[];
  default_speed_mps: number;
  template_parameters: Record<string, number>;
}

// mirrors backend/rogue/domain/mission.py:MissionStartPolicy
export type MissionStartPolicy = "at_scenario_start" | "at_time_offset" | "on_event" | "manual";

// mirrors backend/rogue/domain/mission.py:DroneMission
export interface DroneMission {
  id: string;
  name: string;
  platform: Platform;
  trajectory: Trajectory;
  start_policy: MissionStartPolicy;
  start_time_offset: string | null; // ISO8601 duration
  rf_links: DroneRfLink[];
}

// -------------------------------------------------------------------- rf

// mirrors backend/rogue/domain/rf.py:RfLinkRole
export type RfLinkRole = "c2" | "telemetry" | "video" | "data";

// mirrors backend/rogue/domain/rf.py:RfBand
export interface RfBand {
  freq_min_hz: number;
  freq_max_hz: number;
  allowed_channels_hz: number[];
}

// mirrors backend/rogue/domain/recording.py:RecordingReference
export interface RecordingReference {
  recording_id: string;
  version: number;
  note: string | null;
}

// mirrors backend/rogue/domain/recording.py:AccessClassification
export type AccessClassification = "public" | "restricted" | "controlled";

// mirrors backend/rogue/domain/recording.py:IQRecording — the M4 catalogue
// entry shape returned by GET /recordings (src/api/recordings.ts). Not the
// same thing as RecordingReference above, which is just an
// {id, version} pointer an RfEmission embeds.
export interface IQRecording {
  id: string;
  version: number;
  metadata_object_key: string;
  data_object_key: string;
  sha256_metadata: string;
  sha256_data: string;
  sample_format: string;
  sample_rate_hz: number;
  sample_count: number;
  duration_s: number;
  center_frequency_hz: number | null;
  provenance: string | null;
  access_classification: AccessClassification;
  allowed_use_constraints: string[];
  allowed_frequency_min_hz: number | null;
  allowed_frequency_max_hz: number | null;
  extra_sigmf_fields: Record<string, unknown>;
}

// mirrors backend/rogue/domain/rf.py:RfEmission
export interface RfEmission {
  id: string;
  recording: RecordingReference;
  start_offset: string; // ISO8601 duration
  duration_override: string | null;
  gain_offset_db: number;
  loop: boolean;
  notes: string | null;
}

// mirrors backend/rogue/domain/rf.py:FrequencySwitchingMode
export type FrequencySwitchingMode =
  "scripted" | "mission_triggered" | "probabilistic_adaptive" | "external_state_triggered";

// mirrors backend/rogue/domain/rf.py:FrequencyTransitionType
export type FrequencyTransitionType = "channel_switch" | "band_switch";

// mirrors backend/rogue/domain/rf.py:ScriptedFrequencyChange
export interface ScriptedFrequencyChange {
  at_offset: string; // ISO8601 duration
  frequency_hz: number;
  transition_type: FrequencyTransitionType;
}

// mirrors backend/rogue/domain/rf.py:FrequencyBehaviour
export interface FrequencyBehaviour {
  mode: FrequencySwitchingMode;
  scripted_changes: ScriptedFrequencyChange[];
  mission_trigger_anchor: string | null;
  random_seed: number | null;
  mean_dwell_s: number | null;
  external_trigger_reference: string | null;
}

// mirrors backend/rogue/domain/rf.py:TimingSyncClass
export type TimingSyncClass =
  | "l0_simulated"
  | "l1_software_barrier"
  | "l2_scheduled_local"
  | "l3_shared_reference"
  | "l4_measured";

// mirrors backend/rogue/domain/rf.py:ResourcePreference
export interface ResourcePreference {
  preferred_agent_tags: string[];
  required_sync_class: TimingSyncClass | null;
  notes: string | null;
}

// mirrors backend/rogue/domain/rf.py:DroneRfLink
export interface DroneRfLink {
  id: string;
  role: RfLinkRole;
  band: RfBand;
  frequency_behaviour: FrequencyBehaviour;
  emissions: RfEmission[];
  resource_preference: ResourcePreference | null;
}

// -------------------------------------------------------------- receiver

// mirrors backend/rogue/domain/receiver.py:ReceiverType
export type ReceiverType = "monitor" | "tdoa" | "aoa_doa";

// mirrors backend/rogue/domain/receiver.py:Receiver
export interface Receiver {
  id: string;
  name: string;
  receiver_type: ReceiverType;
  position: GeoPoint;
  array_group_id: string | null;
  element_index: number | null;
  element_local_offset_m: [number, number, number] | null;
}

// -------------------------------------------------------------- timeline

// mirrors backend/rogue/domain/timeline.py:MissionRelativeAnchor
export type MissionRelativeAnchor =
  "mission_start" | "waypoint" | "area_entry" | "phase_completion";

// mirrors backend/rogue/domain/timeline.py:SafetyEventKind
export type SafetyEventKind =
  | "lease_expiry"
  | "alarm"
  | "clock_degradation"
  | "underrun"
  | "no_transmit_violation"
  | "emergency_stop";

interface TimelineEventBase {
  id: string;
  label: string | null;
  notes: string | null;
}

export interface AbsoluteTimelineEvent extends TimelineEventBase {
  kind: "absolute";
  scenario_time_offset: string; // ISO8601 duration
}

export interface MissionRelativeTimelineEvent extends TimelineEventBase {
  kind: "mission_relative";
  mission_id: string;
  anchor: MissionRelativeAnchor;
  waypoint_sequence_index: number | null;
  offset: string; // ISO8601 duration
}

export interface ManualGatedTimelineEvent extends TimelineEventBase {
  kind: "manual_gated";
  gate_description: string;
}

export interface ExternalTimelineEvent extends TimelineEventBase {
  kind: "external";
  source: string;
  trigger_reference: string;
}

export interface SafetyTimelineEvent extends TimelineEventBase {
  kind: "safety";
  safety_kind: SafetyEventKind;
  scenario_time_offset: string | null;
}

// mirrors backend/rogue/domain/timeline.py:TimelineEvent (discriminated union)
export type TimelineEvent =
  | AbsoluteTimelineEvent
  | MissionRelativeTimelineEvent
  | ManualGatedTimelineEvent
  | ExternalTimelineEvent
  | SafetyTimelineEvent;

// -------------------------------------------------------------- scenario

// mirrors backend/rogue/domain/scenario.py:Scenario
export interface Scenario {
  id: string;
  name: string;
  owner: string;
  tags: string[];
  coordinate_system: string;
  area_of_operation: GeoPolygon;
  variables: Record<string, unknown>;
  current_version_id: string | null;
  created_at: string;
  updated_at: string;
}

/** Content fields shared by ScenarioDraft and ScenarioVersion. */
export interface ScenarioContent {
  zones: Zone[];
  missions: DroneMission[];
  receivers: Receiver[];
  timeline_events: TimelineEvent[];
  recordings: RecordingReference[];
}

// mirrors backend/rogue/domain/scenario.py:ScenarioDraft
export interface ScenarioDraft extends ScenarioContent {
  id: string;
  scenario_id: string;
  base_version_id: string | null;
  revision: number;
  author: string;
  created_at: string;
  updated_at: string;
}

// mirrors backend/rogue/domain/validation.py:ValidationSeverity
export type ValidationSeverity = "warning" | "blocking";

// mirrors backend/rogue/domain/validation.py:ValidationFinding
export interface ValidationFinding {
  severity: ValidationSeverity;
  code: string;
  message: string;
  path: string;
}

// mirrors backend/rogue/domain/scenario.py:ScenarioVersion
export interface ScenarioVersion extends ScenarioContent {
  id: string;
  scenario_id: string;
  version_number: number;
  schema_version: string;
  author: string;
  change_note: string | null;
  validation_findings: ValidationFinding[];
}
