import React, { useRef, useState } from "react";
import { View, Text, Pressable } from "react-native";
import { CameraView, useCameraPermissions } from "expo-camera";

export default function CameraScreen(props: { onCaptured: (uri: string) => void }) {
  const camRef = useRef<CameraView>(null);
  const [permission, requestPermission] = useCameraPermissions();
  const [busy, setBusy] = useState(false);

  if (!permission?.granted) {
    return (
      <View style={{ gap: 12 }}>
        <Text>Camera permission is required.</Text>
        <Pressable onPress={requestPermission} style={{ padding: 12, borderWidth: 1, borderRadius: 12 }}>
          <Text>Grant permission</Text>
        </Pressable>
      </View>
    );
  }

  const snap = async () => {
    if (busy) return;
    setBusy(true);
    const photo = await camRef.current?.takePictureAsync({ quality: 0.8, skipProcessing: true });
    setBusy(false);
    if (photo?.uri) props.onCaptured(photo.uri);
  };

  return (
    <View style={{ flex: 1, gap: 12 }}>
      <Text>Tips: face a window, remove heavy makeup, keep phone steady.</Text>
      <View style={{ flex: 1, borderRadius: 16, overflow: "hidden" }}>
        <CameraView ref={camRef} style={{ flex: 1 }} facing="front" />
        {/* Overlay guide */}
        <View style={{ position: "absolute", left: 24, right: 24, top: 80, bottom: 160, borderWidth: 2, borderRadius: 24 }} />
      </View>
      <Pressable onPress={snap} style={{ padding: 14, borderRadius: 12, backgroundColor: "black" }}>
        <Text style={{ color: "white", textAlign: "center", fontWeight: "700" }}>{busy ? "…" : "Capture"}</Text>
      </Pressable>
    </View>
  );
}
