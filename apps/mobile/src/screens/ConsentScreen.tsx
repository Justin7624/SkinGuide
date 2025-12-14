import React from "react";
import { View, Text, Switch, Pressable } from "react-native";
import { Consent } from "../state";
import { upsertConsent } from "../api";

export default function ConsentScreen(props: {
  apiBaseUrl: string;
  sessionId: string;
  consent: Consent;
  onChangeConsent: (c: Consent) => void;
  onContinue: () => void;
}) {
  const { apiBaseUrl, sessionId, consent } = props;

  const save = async (next: Consent) => {
    props.onChangeConsent(next);
    await upsertConsent(apiBaseUrl, sessionId, next);
  };

  return (
    <View style={{ gap: 12 }}>
      <Text style={{ fontSize: 16, fontWeight: "700" }}>Before you scan</Text>
      <Text>
        This app provides cosmetic/appearance guidance only. It is not a medical diagnosis or medical advice.
      </Text>

      <View style={{ padding: 12, borderWidth: 1, borderRadius: 12 }}>
        <Text style={{ fontWeight: "700" }}>Store photos for progress</Text>
        <Text style={{ marginTop: 6 }}>
          Default is OFF. If enabled, we store your cropped ROI image for progress tracking and model improvement.
        </Text>
        <Switch
          value={consent.store_progress_images}
          onValueChange={(v) => save({ ...consent, store_progress_images: v })}
        />
      </View>

      <View style={{ padding: 12, borderWidth: 1, borderRadius: 12 }}>
        <Text style={{ fontWeight: "700" }}>Donate anonymized data to improve the AI</Text>
        <Text style={{ marginTop: 6 }}>
          Optional. Helps us improve performance and fairness across skin tones. Default OFF.
        </Text>
        <Switch
          value={consent.donate_for_improvement}
          onValueChange={(v) => save({ ...consent, donate_for_improvement: v })}
        />
      </View>

      <Pressable
        onPress={props.onContinue}
        style={{ padding: 14, borderRadius: 12, backgroundColor: "black" }}
      >
        <Text style={{ color: "white", textAlign: "center", fontWeight: "700" }}>Continue</Text>
      </Pressable>
    </View>
  );
}
