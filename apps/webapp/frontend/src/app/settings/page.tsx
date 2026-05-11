import { Suspense } from "react";

import { SettingsPageRoute } from "@/components/settings/settings-page-route";

export default function SettingsPage() {
  return (
    <Suspense fallback={<div>Loading settings...</div>}>
      <SettingsPageRoute />
    </Suspense>
  );
}
