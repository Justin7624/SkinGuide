// apps/mobile/src/screens/ResultsScreen.tsx

import React from "react";
import { View, Text, Pressable, ScrollView } from "react-native";

function topAttrs(attrs: any[], n: number) {
  if (!Array.isArray(attrs)) return [];
  return [...attrs].sort((a, b) => (b.score ?? 0) - (a.score ?? 0)).slice(0, n);
}

function donationText(d: any) {
  if (!d?.enabled) return "Donation: OFF (not opted in)";
  if (d?.stored) return "Donation: ✅ Stored (ROI-only)";
  if (d?.reason === "already_donated") return "Donation: ✅ Already donated (ROI-only)";
  return `Donation: ❌ Not stored (${d?.reason ?? "unknown"})`;
}

export default function ResultsScreen(props: {
  result: any;
  onNewScan: () => void;
  onLabelScan: () => void;
  canLabel: boolean;
}) {
  const r = props.result;

  return (
    <ScrollView contentContainerStyle={{ gap: 12, paddingBottom: 40 }}>
      <Text style={{ fontSize: 16, fontWeight: "700" }}>Results</Text>
      <Text>{r.disclaimer}</Text>
      <Text>Model: {r.model_version}</Text>
      {r.stored_for_progress ? <Text>✅ Stored for progress (opt-in)</Text> : <Text>🛡️ Not stored</Text>}
      {r.roi_sha256 ? <Text selectable>ROI id: {r.roi_sha256}</Text> : null}

      <View style={{ padding: 12, borderWidth: 1, borderRadius: 12 }}>
        <Text style={{ fontWeight: "700" }}>AI improvement</Text>
        <Text>{donationText(r.donation)}</Text>
        {!props.canLabel && (
          <Text style={{ marginTop: 6, opacity: 0.75 }}>
            Labeling is enabled only when the scan was donated (ROI-only) so your labels attach to a stored sample.
          </Text>
        )}
      </View>

      <View style={{ padding: 12, borderWidth: 1, borderRadius: 12 }}>
        <Text style={{ fontWeight: "700" }}>Overall quality</Text>
        <Text>
          Lighting: {r.quality?.lighting} • Blur: {r.quality?.blur} • Angle: {r.quality?.angle}
        </Text>
      </View>

      <View style={{ padding: 12, borderWidth: 1, borderRadius: 12 }}>
        <Text style={{ fontWeight: "700" }}>Overall appearance attributes</Text>
        {Array.isArray(r.attributes) && r.attributes.length ? (
          r.attributes.map((a: any) => (
            <Text key={a.key}>
              {a.key}: {Math.round(a.score * 100)}% (conf {Math.round(a.confidence * 100)}%)
            </Text>
          ))
        ) : (
          <Text>—</Text>
        )}
      </View>

      <View style={{ padding: 12, borderWidth: 1, borderRadius: 12 }}>
        <Text style={{ fontWeight: "700" }}>Region breakdown</Text>

        {Array.isArray(r.regions) && r.regions.length ? (
          r.regions.map((reg: any) => {
            const tops = topAttrs(reg.attributes, 3);
            return (
              <View key={reg.name} style={{ marginTop: 10, paddingTop: 10, borderTopWidth: 1 }}>
                <Text style={{ fontWeight: "700" }}>
                  {reg.name} {reg.status === "insufficient_skin" ? "(insufficient skin pixels)" : ""}
                </Text>
                <Text style={{ marginTop: 4 }}>
                  Lighting: {reg.quality?.lighting} • Blur: {reg.quality?.blur}
                </Text>
                {tops.length ? (
                  tops.map((a: any) => (
                    <Text key={`${reg.name}-${a.key}`}>
                      • {a.key}: {Math.round(a.score * 100)}% (conf {Math.round(a.confidence * 100)}%)
                    </Text>
                  ))
                ) : (
                  <Text style={{ marginTop: 4 }}>• No region attributes available</Text>
                )}
              </View>
            );
          })
        ) : (
          <Text style={{ marginTop: 6 }}>—</Text>
        )}
      </View>

      <View style={{ padding: 12, borderWidth: 1, borderRadius: 12 }}>
        <Text style={{ fontWeight: "700" }}>Routine</Text>
        <Text style={{ marginTop: 6, fontWeight: "700" }}>AM</Text>
        {r.routine?.AM?.map?.((x: string) => <Text key={`am-${x}`}>• {x}</Text>) ?? <Text>—</Text>}
        <Text style={{ marginTop: 6, fontWeight: "700" }}>PM</Text>
        {r.routine?.PM?.map?.((x: string) => <Text key={`pm-${x}`}>• {x}</Text>) ?? <Text>—</Text>}
      </View>

      <View style={{ flexDirection: "row", gap: 12 }}>
        <Pressable onPress={props.onNewScan} style={{ flex: 1, padding: 14, borderRadius: 12, backgroundColor: "black" }}>
          <Text style={{ color: "white", textAlign: "center", fontWeight: "700" }}>New scan</Text>
        </Pressable>

        <Pressable
          onPress={props.onLabelScan}
          disabled={!props.canLabel}
          style={{
            flex: 1,
            padding: 14,
            borderRadius: 12,
            borderWidth: 1,
            opacity: props.canLabel ? 1 : 0.5,
          }}
        >
          <Text style={{ textAlign: "center", fontWeight: "700" }}>Label scan</Text>
        </Pressable>
      </View>
    </ScrollView>
  );
}
