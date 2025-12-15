// apps/mobile/src/screens/LabelScreen.tsx

import React, { useMemo, useState } from "react";
import { View, Text, Pressable, ScrollView, Alert } from "react-native";
import { labelSample } from "../api";

type AttributeKey =
  | "uneven_tone_appearance"
  | "hyperpigmentation_appearance"
  | "redness_appearance"
  | "texture_roughness_appearance"
  | "shine_oiliness_appearance"
  | "pore_visibility_appearance"
  | "fine_lines_appearance"
  | "dryness_flaking_appearance";

const ATTRS: { key: AttributeKey; label: string }[] = [
  { key: "uneven_tone_appearance", label: "Uneven tone (appearance)" },
  { key: "hyperpigmentation_appearance", label: "Hyperpigmentation (appearance)" },
  { key: "redness_appearance", label: "Redness (appearance)" },
  { key: "texture_roughness_appearance", label: "Texture/roughness (appearance)" },
  { key: "shine_oiliness_appearance", label: "Shine/oiliness (appearance)" },
  { key: "pore_visibility_appearance", label: "Pore visibility (appearance)" },
  { key: "fine_lines_appearance", label: "Fine lines (appearance)" },
  { key: "dryness_flaking_appearance", label: "Dryness/flaking (appearance)" },
];

type Severity = "none" | "mild" | "moderate" | "severe";

function sevToValue(s: Severity): number | null {
  if (s === "none") return null;      // omit from sparse labels
  if (s === "mild") return 0.33;
  if (s === "moderate") return 0.66;
  return 1.0;
}

function Chip(props: { text: string; active?: boolean; onPress: () => void }) {
  return (
    <Pressable
      onPress={props.onPress}
      style={{
        paddingVertical: 8,
        paddingHorizontal: 10,
        borderRadius: 999,
        borderWidth: 1,
        backgroundColor: props.active ? "black" : "transparent",
      }}
    >
      <Text style={{ color: props.active ? "white" : "black", fontWeight: "600" }}>{props.text}</Text>
    </Pressable>
  );
}

export default function LabelScreen(props: {
  apiBaseUrl: string;
  sessionId: string;
  roiSha256: string;
  onBack: () => void;
  onDone: () => void;
}) {
  const [busy, setBusy] = useState(false);

  const [sev, setSev] = useState<Record<AttributeKey, Severity>>(() => {
    const init: any = {};
    for (const a of ATTRS) init[a.key] = "none";
    return init;
  });

  const [fitzpatrick, setFitzpatrick] = useState<"I" | "II" | "III" | "IV" | "V" | "VI" | null>(null);
  const [ageBand, setAgeBand] = useState<
    "<18" | "18-24" | "25-34" | "35-44" | "45-54" | "55-64" | "65+" | null
  >(null);

  const sparseLabels = useMemo(() => {
    const out: Record<string, number> = {};
    for (const a of ATTRS) {
      const v = sevToValue(sev[a.key]);
      if (v !== null) out[a.key] = v;
    }
    return out;
  }, [sev]);

  const submit = async () => {
    if (!props.roiSha256) {
      Alert.alert("Missing ROI id", "Run a scan first, then label it.");
      return;
    }
    if (Object.keys(sparseLabels).length === 0) {
      Alert.alert("Nothing selected", "Pick at least one attribute severity, or go back.");
      return;
    }

    setBusy(true);
    try {
      const resp = await labelSample(props.apiBaseUrl, props.sessionId, {
        roi_sha256: props.roiSha256,
        labels: sparseLabels,
        fitzpatrick: fitzpatrick ?? undefined,
        age_band: ageBand ?? undefined,
      });

      if (resp?.stored) {
        Alert.alert("Thanks!", "Label saved for model improvement.");
        props.onDone();
      } else {
        Alert.alert(
          "Not saved",
          `Reason: ${resp?.reason ?? "unknown"}\n\n(Labels require opt-in donation consent and a donated sample.)`
        );
      }
    } catch (e: any) {
      Alert.alert("Error", e?.message ?? "Failed to submit labels.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <ScrollView contentContainerStyle={{ gap: 12, paddingBottom: 40 }}>
      <Text style={{ fontSize: 16, fontWeight: "700" }}>Help improve the AI</Text>
      <Text>
        This is optional. You’re labeling the *appearance* in your ROI-only scan to help train the model.
        It’s not a diagnosis.
      </Text>

      <View style={{ padding: 12, borderWidth: 1, borderRadius: 12 }}>
        <Text style={{ fontWeight: "700" }}>Scan ID</Text>
        <Text selectable>{props.roiSha256}</Text>
      </View>

      <View style={{ padding: 12, borderWidth: 1, borderRadius: 12, gap: 8 }}>
        <Text style={{ fontWeight: "700" }}>Optional: skin tone (Fitzpatrick)</Text>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
          {(["I", "II", "III", "IV", "V", "VI"] as const).map((x) => (
            <Chip key={x} text={x} active={fitzpatrick === x} onPress={() => setFitzpatrick(fitzpatrick === x ? null : x)} />
          ))}
        </View>
        <Text style={{ marginTop: 6, opacity: 0.75 }}>
          Only provide if you want—used for fairness testing, not personalization.
        </Text>
      </View>

      <View style={{ padding: 12, borderWidth: 1, borderRadius: 12, gap: 8 }}>
        <Text style={{ fontWeight: "700" }}>Optional: age band</Text>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
          {(["<18", "18-24", "25-34", "35-44", "45-54", "55-64", "65+"] as const).map((x) => (
            <Chip key={x} text={x} active={ageBand === x} onPress={() => setAgeBand(ageBand === x ? null : x)} />
          ))}
        </View>
      </View>

      <View style={{ padding: 12, borderWidth: 1, borderRadius: 12, gap: 10 }}>
        <Text style={{ fontWeight: "700" }}>Attribute severities</Text>

        {ATTRS.map((a) => (
          <View key={a.key} style={{ gap: 8 }}>
            <Text style={{ fontWeight: "600" }}>{a.label}</Text>
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
              {(["none", "mild", "moderate", "severe"] as const).map((s) => (
                <Chip
                  key={`${a.key}-${s}`}
                  text={s}
                  active={sev[a.key] === s}
                  onPress={() => setSev((p) => ({ ...p, [a.key]: s }))}
                />
              ))}
            </View>
          </View>
        ))}
      </View>

      <View style={{ flexDirection: "row", gap: 12 }}>
        <Pressable onPress={props.onBack} style={{ flex: 1, padding: 14, borderWidth: 1, borderRadius: 12 }}>
          <Text style={{ textAlign: "center" }}>Back</Text>
        </Pressable>
        <Pressable
          onPress={submit}
          disabled={busy}
          style={{
            flex: 1,
            padding: 14,
            borderRadius: 12,
            backgroundColor: "black",
            opacity: busy ? 0.6 : 1,
          }}
        >
          <Text style={{ color: "white", textAlign: "center", fontWeight: "700" }}>
            {busy ? "Submitting…" : "Submit labels"}
          </Text>
        </Pressable>
      </View>
    </ScrollView>
  );
}
