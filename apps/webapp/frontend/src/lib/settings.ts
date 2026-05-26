export type SettingsProviderRecord = {
  key: string;
  label: string;
  enabled: boolean;
  provider_kind: "native" | "openai_compatible";
  base_url: string | null;
  api_key_env: string | null;
  has_api_key: boolean;
  models: string[];
  test_model: string | null;
  template_key: string | null;
  api_key?: string;
  models_text?: string;
};

export type SettingsTemplateRecord = {
  key: string;
  provider_key: string | null;
  label: string;
  provider_kind: "native" | "openai_compatible";
  base_url: string | null;
  api_key_env: string | null;
};

export type SettingsModelsResponse = {
  default_model: string | null;
  providers: SettingsProviderRecord[];
  templates: SettingsTemplateRecord[];
};

export type SettingsModelsUpdateRequest = {
  default_model: string | null;
  providers: Array<{
    key: string;
    label: string;
    enabled: boolean;
    provider_kind: "native" | "openai_compatible";
    base_url: string | null;
    api_key_env: string | null;
    api_key: string;
    models: string[];
    test_model: string;
    template_key: string | null;
  }>;
};

export type SettingsModelTestRequest = {
  provider: SettingsModelsUpdateRequest["providers"][number];
  model: string;
};

export type SettingsModelTestResponse = {
  ok: boolean;
  provider_key: string;
  model: string;
  message: string;
};

export type AppearanceSettingsResponse = {
  theme_modes: string[];
  storage: string;
  default_theme: string;
};

export function normalizeProviderForEditor(
  provider: SettingsProviderRecord,
): SettingsProviderRecord {
  return {
    ...provider,
    api_key: "",
    models_text: provider.models.join("\n"),
  };
}

export function buildProviderFromTemplate(
  template: SettingsTemplateRecord,
  existingProviders: SettingsProviderRecord[],
): SettingsProviderRecord {
  const relayIndex = existingProviders.filter((provider) =>
    provider.key.startsWith("relay_"),
  ).length + 1;
  const key = template.provider_key ?? `relay_${relayIndex}`;
  const label = template.provider_key ? template.label : `自定义中转 ${relayIndex}`;
  const apiKeyEnv =
    template.api_key_env ?? `EPIMINDAGENT_CLI_${key.toUpperCase()}_API_KEY`;
  return normalizeProviderForEditor({
    key,
    label,
    enabled: true,
    provider_kind: template.provider_kind,
    base_url: template.base_url,
    api_key_env: apiKeyEnv,
    has_api_key: false,
    models: [],
    test_model: null,
    template_key: template.key,
  });
}

export function buildSettingsSavePayload(
  defaultModel: string | null,
  providers: SettingsProviderRecord[],
): SettingsModelsUpdateRequest {
  return {
    default_model: defaultModel,
    providers: providers.map((provider) => {
      const models = parseModelsText(provider.models_text ?? provider.models.join("\n"));
      const testModel = (provider.test_model?.trim() || models[0] || "").trim();
      return {
        key: provider.key,
        label: provider.label.trim(),
        enabled: provider.enabled,
        provider_kind: provider.provider_kind,
        base_url: provider.base_url?.trim() || null,
        api_key_env: provider.api_key_env?.trim() || null,
        api_key: provider.api_key?.trim() || "",
        models,
        test_model: testModel,
        template_key: provider.template_key,
      };
    }),
  };
}

export function buildDefaultModelOptions(
  providers: SettingsProviderRecord[],
): Array<{ value: string; label: string }> {
  return providers.flatMap((provider) => {
    if (!provider.enabled) return [];
    return parseModelsText(provider.models_text ?? provider.models.join("\n")).map(
      (model) => ({
        value: `${provider.key}:${model}`,
        label: `${provider.label} / ${model}`,
      }),
    );
  });
}

export function parseModelsText(value: string): string[] {
  return value
    .split(/\r?\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export async function fetchModelSettings(): Promise<SettingsModelsResponse> {
  const response = await fetch("/api/settings/models");
  if (!response.ok) {
    throw new Error("Failed to load model settings.");
  }
  const payload = (await response.json()) as SettingsModelsResponse;
  return {
    default_model: payload.default_model ?? null,
    templates: payload.templates ?? [],
    providers: (payload.providers ?? []).map(normalizeProviderForEditor),
  };
}

export async function saveModelSettings(
  payload: SettingsModelsUpdateRequest,
): Promise<SettingsModelsResponse> {
  const response = await fetch("/api/settings/models", {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail ?? "Failed to save model settings.");
  }
  const next = (await response.json()) as SettingsModelsResponse;
  return {
    default_model: next.default_model ?? null,
    templates: next.templates ?? [],
    providers: (next.providers ?? []).map(normalizeProviderForEditor),
  };
}

export async function testModelSettings(
  payload: SettingsModelTestRequest,
): Promise<SettingsModelTestResponse> {
  const response = await fetch("/api/settings/models/test", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail ?? "Failed to test model settings.");
  }
  return (await response.json()) as SettingsModelTestResponse;
}

export async function fetchAppearanceSettings(): Promise<AppearanceSettingsResponse> {
  const response = await fetch("/api/settings/appearance");
  if (!response.ok) {
    throw new Error("Failed to load appearance settings.");
  }
  return (await response.json()) as AppearanceSettingsResponse;
}

export function buildSettingsHref(search: string): string {
  return search ? `/settings${search.startsWith("?") ? search : `?${search}`}` : "/settings";
}

export function buildChatHref(search: string): string {
  return search ? `/${search.startsWith("?") ? search : `?${search}`}` : "/";
}
