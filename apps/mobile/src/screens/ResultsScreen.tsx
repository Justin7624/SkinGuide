import React from "react";
import { View, Text, Pressable, ScrollView } from "react-native";

export default function ResultsScreen(props: { result: any; onNewScan: () => void }) {
  const r = props.result;

  return (
    <ScrollView contentContainerStyle={{ gap: 12 }}>
      <Text style={{ fontSize: 16, fontWeight: "700" }}>Results</Text>
      <Text>{r.disclaimer}</Text>
      <Text>Model: {r.model_version}</Text>
      {r.stored_for_progress ? <Text>✅ Stored for progress (opt-in)</Text> : <Text>🛡️ Not stored</Text>}

      <View style={{ padding: 12, borderWidth: 1, borderRadius: 12 }}>
        <Text style={{ fontWeight: "700" }}>Quality</Text>
        <Text>Lighting: {r.quality.lighting} • Blur: {r.quality.blur} • Angle: {r.quality.angle}</Text>
      </View>

      <View style={{ padding: 12, borderWidth: 1, borderRadius: 12 }}>
        <Text style={{ fontWeight: "700" }}>Appearance attributes</Text>
        {r.attributes.map((a: any) => (
          <Text key={a.key}>
            {a.key}: {Math.round(a.score * 100)}% (conf {Math.round(a.confidence * 100)}%)
          </Text>
        ))}
      </View>

      <View style={{ padding: 12, borderWidth: 1, borderRadius: 12 }}>
        <Text style={{ fontWeight: "700" }}>Routine</Text>
        <Text style={{ marginTop: 6, fontWeight: "700" }}>AM</Text>
        {r.routine.AM.map((x: string) => <Text key={`am-${x}`}>• {x}</Text>)}
        <Text style={{ marginTop: 6, fontWeight: "700" }}>PM</Text>
        {r.routine.PM.map((x: string) => <Text key={`pm-${x}`}>• {x}</Text>)}
      </View>

      <View style={{ padding: 12, borderWidth: 1, borderRadius: 12 }}>
        <Text style={{ fontWeight: "700" }}>Professional options to discuss</Text>
        {r.professional_to_discuss.length ? r.professional_to_discuss.map((x: string) => <Text key={x}>• {x}</Text>) : <Text>—</Text>}
      </View>

      <View style={{ padding: 12, borderWidth: 1, borderRadius: 12 }}>
        <Text style={{ fontWeight: "700" }}>When to seek care</Text>
        {r.when_to_seek_care.map((x: string) => <Text key={x}>• {x}</Text>)}
      </View>

      <Pressable onPress={props.onNewScan} style={{ padding: 14, borderRadius: 12, backgroundColor: "black" }}>
        <Text style={{ color: "white", textAlign: "center", fontWeight: "700" }}>New scan</Text>
      </Pressable>
    </ScrollView>
  );
}
