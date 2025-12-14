import React, { useEffect, useState } from "react";
import { SafeAreaView, View, Text, Pressable } from "react-native";
import { defaultState } from "./src/state";
import { createSession } from "./src/api";
import ConsentScreen from "./src/screens/ConsentScreen";
import CameraScreen from "./src/screens/CameraScreen";
import ReviewScreen from "./src/screens/ReviewScreen";
import ResultsScreen from "./src/screens/ResultsScreen";
import SettingsScreen from "./src/screens/SettingsScreen";

type Screen = "consent" | "camera" | "review" | "results" | "settings";

export default function App() {
  const [st, setSt] = useState(defaultState);
  const [screen, setScreen] = useState<Screen>("consent");
  const [photoUri, setPhotoUri] = useState<string | null>(null);
  const [result, setResult] = useState<any>(null);

  useEffect(() => {
    (async () => {
      if (!st.sessionId) {
        const s = await createSession(st.apiBaseUrl);
        setSt((p) => ({ ...p, sessionId: s.session_id }));
      }
    })();
  }, [st.apiBaseUrl, st.sessionId]);

  if (!st.sessionId) {
    return (
      <SafeAreaView style={{ flex: 1, justifyContent: "center", alignItems: "center" }}>
        <Text>Starting…</Text>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={{ flex: 1, padding: 16 }}>
      <View style={{ flexDirection: "row", justifyContent: "space-between", marginBottom: 12 }}>
        <Text style={{ fontSize: 18, fontWeight: "700" }}>SkinGuide</Text>
        <Pressable onPress={() => setScreen("settings")}>
          <Text style={{ fontSize: 16 }}>Settings</Text>
        </Pressable>
      </View>

      {screen === "consent" && (
        <ConsentScreen
          apiBaseUrl={st.apiBaseUrl}
          sessionId={st.sessionId}
          consent={st.consent}
          onChangeConsent={(consent) => setSt((p) => ({ ...p, consent }))}
          onContinue={() => setScreen("camera")}
        />
      )}

      {screen === "camera" && (
        <CameraScreen
          onCaptured={(uri) => {
            setPhotoUri(uri);
            setScreen("review");
          }}
        />
      )}

      {screen === "review" && photoUri && (
        <ReviewScreen
          apiBaseUrl={st.apiBaseUrl}
          sessionId={st.sessionId}
          photoUri={photoUri}
          onBack={() => setScreen("camera")}
          onResult={(r) => {
            setResult(r);
            setScreen("results");
          }}
        />
      )}

      {screen === "results" && result && (
        <ResultsScreen
          result={result}
          onNewScan={() => {
            setResult(null);
            setPhotoUri(null);
            setScreen("camera");
          }}
        />
      )}

      {screen === "settings" && (
        <SettingsScreen
          apiBaseUrl={st.apiBaseUrl}
          sessionId={st.sessionId}
          onBack={() => setScreen("consent")}
        />
      )}
    </SafeAreaView>
  );
}
