import type { Receiver, ReceiverType } from "../../domain/types";
import { NumberField, SelectField, TextField } from "./fields";

const RECEIVER_TYPES: readonly ReceiverType[] = ["monitor", "tdoa", "aoa_doa"];

export interface ReceiverFormProps {
  receiver: Receiver;
  onChange: (receiver: Receiver) => void;
  onDelete: () => void;
}

export function ReceiverForm({ receiver, onChange, onDelete }: ReceiverFormProps) {
  const coords = receiver.position.coordinates;
  const offset = receiver.element_local_offset_m ?? [0, 0, 0];
  const isArrayType = receiver.receiver_type === "tdoa" || receiver.receiver_type === "aoa_doa";

  function setReceiverType(receiver_type: ReceiverType) {
    onChange({
      ...receiver,
      receiver_type,
      array_group_id:
        receiver_type === "tdoa" || receiver_type === "aoa_doa"
          ? (receiver.array_group_id ?? crypto.randomUUID())
          : null,
      element_local_offset_m: receiver_type === "aoa_doa" ? [0, 0, 0] : null,
    });
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, padding: 16 }}>
      <h3 style={{ margin: 0 }}>Receiver</h3>
      <TextField
        label="Name"
        value={receiver.name}
        onChange={(name) => onChange({ ...receiver, name })}
      />
      <SelectField
        label="Type"
        value={receiver.receiver_type}
        options={RECEIVER_TYPES}
        onChange={setReceiverType}
      />
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <NumberField
          label="Lon"
          value={coords[0]}
          step={0.0001}
          onChange={(lon) =>
            onChange({ ...receiver, position: { type: "Point", coordinates: [lon, coords[1]] } })
          }
        />
        <NumberField
          label="Lat"
          value={coords[1]}
          step={0.0001}
          onChange={(lat) =>
            onChange({ ...receiver, position: { type: "Point", coordinates: [coords[0], lat] } })
          }
        />
      </div>
      {isArrayType && (
        <TextField
          label="Array group ID"
          value={receiver.array_group_id ?? ""}
          onChange={(array_group_id) => onChange({ ...receiver, array_group_id })}
        />
      )}
      {receiver.receiver_type === "aoa_doa" && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <NumberField
            label="Offset E (m)"
            value={offset[0]}
            onChange={(e) =>
              onChange({ ...receiver, element_local_offset_m: [e, offset[1], offset[2]] })
            }
          />
          <NumberField
            label="Offset N (m)"
            value={offset[1]}
            onChange={(n) =>
              onChange({ ...receiver, element_local_offset_m: [offset[0], n, offset[2]] })
            }
          />
          <NumberField
            label="Offset U (m)"
            value={offset[2]}
            onChange={(u) =>
              onChange({ ...receiver, element_local_offset_m: [offset[0], offset[1], u] })
            }
          />
        </div>
      )}
      <button type="button" onClick={onDelete} style={{ alignSelf: "flex-start" }}>
        Delete receiver
      </button>
    </div>
  );
}
