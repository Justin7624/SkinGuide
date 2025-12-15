// apps/mobile/src/screens/ResultsScreen.tsx

import React from "react";
import { View, Text, Pressable, ScrollView } from "react-native";

function topAttrs(attrs: any[], n: number) {
  if (!Array.isArray(attrs)) return [];
  return [...attrs].sort((a, b) => (b.score ?? 0) - (a.score ?? 0)).slice(0, n);
}

export default function ResultsScreen(props: { result: any; onNewScan: () => void }) {
  const r = props.result;

  return (
    <ScrollView contentContainerStyle={{ gap: 12, paddingBottom: 40 }}>
      <Text style={{ fontSize: 16, fontWeight: "700" }}>Results</Text>
      <Text>{r.disclaimer}</Text>
      <Text>Model: {r.model_version}</Text>
      {r.stored_for_progress ? <Text>✅ Stored for progress (opt-in)</Text> : <Text>🛡️ Not stored</Text>}

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

      <View style={{ padding: 12, borderWidth: 1, borderRadius: 12 }}>
        <Text style={{ fontWeight: "700" }}>Professional options to discuss</Text>
        {Array.isArray(r.professional_to_discuss) && r.professional_to_discuss.length ? (
          r.professional_to_discuss.map((x: string) => <Text key={x}>• {x}</Text>)
        ) : (
          <Text>—</Text>
        )}
      </View>

      <View style={{ padding: 12, borderWidth: 1, borderRadius: 12 }}>
        <Text style={{ fontWeight: "700" }}>When to seek care</Text>
        {Array.isArray(r.when_to_seek_care) && r.when_to_seek_care.length ? (
          r.when_to_seek_care.map((x: string) => <Text key={x}>• {x}</Text>)
        ) : (
          <Text>—</Text>
        )}
      </View>

      <Pressable onPress={props.onNewScan} style={{ padding: 14, borderRadius: 12, backgroundColor: "black" }}>
        <Text style={{ color: "white", textAlign: "center", fontWeight: "700" }}>New scan</Text>
      </Pressable>
    </ScrollView>
  );
}
