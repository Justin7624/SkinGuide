import React, { useState } from "react";
import { View, Text, Image, Pressable } from "react-native";
import * as ImageManipulator from "expo-image-manipulator";
import { analyze } from "../api";

export default function ReviewScreen(props: {
  apiBaseUrl: string;
  sessionId: string;
  photoUri: string;
  onBack: () => void;
  onResult: (r: any) => void;
}) {
  const [busy, setBusy] = useState(false);

  const centerCropToJpeg = async (uri: string) => {
    // Simple ROI-only strategy: center crop (privacy-friendly), then resize.
    const manip = await ImageManipulator.manipulateAsync(
      uri,
      [{ resize: { width: 1024 } }],
      { compress: 0.85, format: ImageManipulator.SaveFormat.JPEG }
    );
    // For MVP: upload resized center image (future: crop to face ROI with landmarks)
    return manip.uri;
  };

  const run = async () => {
    setBusy(true);
    try {
      const roiUri = await centerCropToJpeg(props.photoUri);
      const r = await analyze(props.apiBaseUrl, props.sessionId, roiUri);
      props.onResult(r);
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={{ gap: 12 }}>
      <Text style={{ fontWeight: "700" }}>Review</Text>
      <Image source={{ uri: props.photoUri }} style={{ width: "100%", height: 380, borderRadius: 16 }} />
      <Text>
        We’ll upload a resized ROI image for analysis. By default nothing is stored unless you opted in on the consent screen.
      </Text>
      <View style={{ flexDirection: "row", gap: 12 }}>
        <Pressable onPress={props.onBack} style={{ flex: 1, padding: 14, borderWidth: 1, borderRadius: 12 }}>
          <Text style={{ textAlign: "center" }}>Retake</Text>
        </Pressable>
        <Pressable onPress={run} style={{ flex: 1, padding: 14, borderRadius: 12, backgroundColor: "black" }}>
          <Text style={{ color: "white", textAlign: "center", fontWeight: "700" }}>{busy ? "Analyzing…" : "Analyze"}</Text>
        </Pressable>
      </View>
    </View>
  );
}
