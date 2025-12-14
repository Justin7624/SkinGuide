import React, { useState } from "react";
import { View, Text, Pressable } from "react-native";
import { deleteProgress } from "../api";

export default function SettingsScreen(props: { apiBaseUrl: string; sessionId: string; onBack: () => void }) {
  const [busy, setBusy] = useState(false);

  const wipe = async () => {
    setBusy(true);
    try {
      await deleteProgress(props.apiBaseUrl, props.sessionId);
      alert("Deleted stored progress (if any).");
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={{ gap: 12 }}>
      <Text style={{ fontSize: 16, fontWeight: "700" }}>Settings</Text>
      <Text>Session: {props.sessionId}</Text>

      <Pressable onPress={wipe} style={{ padding: 14, borderWidth: 1, borderRadius: 12 }}>
        <Text style={{ textAlign: "center" }}>{busy ? "…" : "Delete stored progress"}</Text>
      </Pressable>

      <Pressable onPress={props.onBack} style={{ padding: 14, borderRadius: 12, backgroundColor: "black" }}>
        <Text style={{ color: "white", textAlign: "center", fontWeight: "700" }}>Back</Text>
      </Pressable>
    </View>
  );
}
