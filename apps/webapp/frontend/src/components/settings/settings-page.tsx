"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, PlugZap, Save, Server, Sparkles, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { AppearanceSettingsSection } from "./appearance-settings";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
  buildDefaultModelOptions,
  buildProviderFromTemplate,
  buildSettingsSavePayload,
  fetchAppearanceSettings,
  fetchModelSettings,
  parseModelsText,
  saveModelSettings,
  type SettingsProviderRecord,
  type SettingsTemplateRecord,
  testModelSettings,
} from "@/lib/settings";

type SettingsSection = "models" | "appearance";

function ProviderList({
  providers,
  selectedProviderKey,
  onSelect,
}: {
  providers: SettingsProviderRecord[];
  selectedProviderKey: string | null;
  onSelect: (providerKey: string) => void;
}) {
  if (providers.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-border p-4 text-sm text-muted-foreground">
        还没有启用的 Provider，先从下方模板添加一个。
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {providers.map((provider) => {
        const active = provider.key === selectedProviderKey;
        return (
          <button
            key={provider.key}
            type="button"
            className={`w-full rounded-xl border px-4 py-3 text-left transition ${
              active
                ? "border-primary bg-primary/5"
                : "border-border bg-card hover:bg-accent"
            }`}
            onClick={() => onSelect(provider.key)}
          >
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="font-medium">{provider.label}</div>
                <div className="text-xs text-muted-foreground">{provider.key}</div>
              </div>
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                {provider.provider_kind === "native" ? (
                  <Sparkles className="size-4" />
                ) : (
                  <Server className="size-4" />
                )}
                {provider.enabled ? "已启用" : "已停用"}
              </div>
            </div>
          </button>
        );
      })}
    </div>
  );
}

function TemplateActions({
  templates,
  providers,
  onAddTemplate,
}: {
  templates: SettingsTemplateRecord[];
  providers: SettingsProviderRecord[];
  onAddTemplate: (template: SettingsTemplateRecord) => void;
}) {
  const existingKeys = new Set(providers.map((provider) => provider.key));
  return (
    <div className="space-y-2">
      {templates.map((template) => {
        const providerKey = template.provider_key;
        const isExisting = providerKey ? existingKeys.has(providerKey) : false;
        const label =
          template.key === "custom_openai_compatible"
            ? "新增自定义中转"
            : `添加 ${template.label}`;
        return (
          <Button
            key={template.key}
            type="button"
            variant="outline"
            className="w-full justify-start"
            disabled={isExisting}
            onClick={() => onAddTemplate(template)}
          >
            <PlugZap className="size-4" />
            {label}
          </Button>
        );
      })}
    </div>
  );
}

export function SettingsPageContent({ backHref }: { backHref: string }) {
  const [activeSection, setActiveSection] = useState<SettingsSection>("models");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [providers, setProviders] = useState<SettingsProviderRecord[]>([]);
  const [templates, setTemplates] = useState<SettingsTemplateRecord[]>([]);
  const [defaultModel, setDefaultModel] = useState<string | null>(null);
  const [selectedProviderKey, setSelectedProviderKey] = useState<string | null>(null);
  const [themeModes, setThemeModes] = useState<string[]>(["light", "dark", "system"]);

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchModelSettings(), fetchAppearanceSettings()])
      .then(([modelsPayload, appearancePayload]) => {
        if (cancelled) return;
        setProviders(modelsPayload.providers);
        setTemplates(modelsPayload.templates);
        setDefaultModel(modelsPayload.default_model);
        setSelectedProviderKey(modelsPayload.providers[0]?.key ?? null);
        setThemeModes(appearancePayload.theme_modes);
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        toast.error("加载设置失败", {
          description: error instanceof Error ? error.message : "未知错误",
        });
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const selectedProvider = providers.find(
    (provider) => provider.key === selectedProviderKey,
  ) ?? null;
  const defaultModelOptions = useMemo(
    () => buildDefaultModelOptions(providers),
    [providers],
  );

  const updateSelectedProvider = (
    updater: (provider: SettingsProviderRecord) => SettingsProviderRecord,
  ) => {
    if (!selectedProvider) return;
    setProviders((current) =>
      current.map((provider) =>
        provider.key === selectedProvider.key ? updater(provider) : provider,
      ),
    );
  };

  const handleAddTemplate = (template: SettingsTemplateRecord) => {
    const provider = buildProviderFromTemplate(template, providers);
    setProviders((current) => [...current, provider]);
    setSelectedProviderKey(provider.key);
    setDefaultModel((current) => current);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const payload = buildSettingsSavePayload(defaultModel, providers);
      const saved = await saveModelSettings(payload);
      setProviders(saved.providers);
      setTemplates(saved.templates);
      setDefaultModel(saved.default_model);
      setSelectedProviderKey((current) =>
        saved.providers.some((provider) => provider.key === current)
          ? current
          : saved.providers[0]?.key ?? null,
      );
      toast.success("模型设置已保存");
    } catch (error) {
      toast.error("保存失败", {
        description: error instanceof Error ? error.message : "未知错误",
      });
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    if (!selectedProvider) return;
    const providerPayload = buildSettingsSavePayload(defaultModel, [selectedProvider]).providers[0];
    if (!providerPayload.test_model) {
      toast.error("请先填写测试模型");
      return;
    }
    setTesting(true);
    try {
      const result = await testModelSettings({
        provider: providerPayload,
        model: providerPayload.test_model,
      });
      if (result.ok) {
        toast.success("测试连接成功", { description: result.model });
      } else {
        toast.error("测试连接失败", { description: result.message });
      }
    } catch (error) {
      toast.error("测试连接失败", {
        description: error instanceof Error ? error.message : "未知错误",
      });
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="mx-auto flex max-w-7xl flex-col gap-6 px-6 py-8">
        <div className="flex items-center justify-between gap-4">
          <Button
            asChild
            variant="ghost"
            className="gap-2"
          >
            <Link href={backHref}>
              <ArrowLeft className="size-4" />
              返回对话
            </Link>
          </Button>
          <div className="text-center">
            <h1 className="text-3xl font-semibold tracking-tight">设置</h1>
            <p className="text-sm text-muted-foreground">
              管理共享模型配置和当前浏览器的外观偏好。
            </p>
          </div>
          <Button
            type="button"
            className="gap-2"
            disabled={saving || activeSection !== "models"}
            onClick={handleSave}
          >
            <Save className="size-4" />
            保存更改
          </Button>
        </div>

        <div className="grid gap-6 lg:grid-cols-[220px_minmax(0,1fr)]">
          <div className="space-y-2 rounded-2xl border bg-card p-3">
            <Button
              type="button"
              variant={activeSection === "models" ? "default" : "ghost"}
              className="w-full justify-start"
              onClick={() => setActiveSection("models")}
            >
              模型配置
            </Button>
            <Button
              type="button"
              variant={activeSection === "appearance" ? "default" : "ghost"}
              className="w-full justify-start"
              onClick={() => setActiveSection("appearance")}
            >
              外观
            </Button>
          </div>

          <div className="rounded-2xl border bg-card p-6 shadow-sm">
            {activeSection === "appearance" ? (
              <AppearanceSettingsSection themeModes={themeModes} />
            ) : (
              <div className="space-y-6">
                <div className="space-y-2">
                  <h2 className="text-2xl font-semibold tracking-tight">模型配置</h2>
                  <p className="text-sm text-muted-foreground">
                    这里的 Provider 和默认模型会写入共享配置，Web、CLI、TUI 共用同一套来源。
                  </p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="default-model">全局默认模型</Label>
                  <select
                    id="default-model"
                    aria-label="全局默认模型"
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                    value={defaultModel ?? ""}
                    onChange={(event) =>
                      setDefaultModel(event.target.value ? event.target.value : null)
                    }
                  >
                    <option value="">未设置</option>
                    {defaultModelOptions.map((option) => (
                      <option
                        key={option.value}
                        value={option.value}
                      >
                        {option.label}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="grid gap-6 xl:grid-cols-[280px_minmax(0,1fr)]">
                  <div className="space-y-4">
                    <ProviderList
                      providers={providers}
                      selectedProviderKey={selectedProviderKey}
                      onSelect={setSelectedProviderKey}
                    />
                    <TemplateActions
                      templates={templates}
                      providers={providers}
                      onAddTemplate={handleAddTemplate}
                    />
                  </div>

                  <div className="rounded-2xl border border-border p-5">
                    {loading ? (
                      <div className="text-sm text-muted-foreground">加载设置中...</div>
                    ) : !selectedProvider ? (
                      <div className="text-sm text-muted-foreground">
                        从左侧选择一个 Provider，或者先添加新的模板。
                      </div>
                    ) : (
                      <div className="space-y-4">
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <div className="text-lg font-medium">{selectedProvider.label}</div>
                            <div className="text-xs text-muted-foreground">
                              {selectedProvider.key}
                            </div>
                          </div>
                          <Button
                            type="button"
                            variant="outline"
                            className="gap-2 text-destructive"
                            onClick={() => {
                              setProviders((current) =>
                                current.filter(
                                  (provider) => provider.key !== selectedProvider.key,
                                ),
                              );
                              setDefaultModel((current) =>
                                current?.startsWith(`${selectedProvider.key}:`)
                                  ? null
                                  : current,
                              );
                              setSelectedProviderKey((current) =>
                                current === selectedProvider.key ? null : current,
                              );
                            }}
                          >
                            <Trash2 className="size-4" />
                            移除 Provider
                          </Button>
                        </div>

                        <div className="grid gap-4 md:grid-cols-2">
                          <div className="space-y-2">
                            <Label htmlFor="provider-label">显示名称</Label>
                            <Input
                              id="provider-label"
                              aria-label="显示名称"
                              value={selectedProvider.label}
                              onChange={(event) =>
                                updateSelectedProvider((provider) => ({
                                  ...provider,
                                  label: event.target.value,
                                }))
                              }
                            />
                          </div>
                          <div className="space-y-2">
                            <Label htmlFor="provider-key">Provider Key</Label>
                            <Input
                              id="provider-key"
                              value={selectedProvider.key}
                              disabled
                            />
                          </div>
                        </div>

                        <div className="flex items-center justify-between rounded-xl border border-border px-4 py-3">
                          <div>
                            <div className="font-medium">启用</div>
                            <div className="text-sm text-muted-foreground">
                              停用后不会出现在全局默认模型列表中。
                            </div>
                          </div>
                          <Switch
                            aria-label="启用开关"
                            checked={selectedProvider.enabled}
                            onCheckedChange={(checked) =>
                              updateSelectedProvider((provider) => ({
                                ...provider,
                                enabled: checked,
                              }))
                            }
                          />
                        </div>

                        <div className="space-y-2">
                          <Label htmlFor="base-url">Base URL</Label>
                          <Input
                            id="base-url"
                            aria-label="Base URL"
                            value={selectedProvider.base_url ?? ""}
                            placeholder={
                              selectedProvider.provider_kind === "openai_compatible"
                                ? "https://your-endpoint/v1"
                                : "可选"
                            }
                            onChange={(event) =>
                              updateSelectedProvider((provider) => ({
                                ...provider,
                                base_url: event.target.value,
                              }))
                            }
                          />
                        </div>

                        <div className="grid gap-4 md:grid-cols-2">
                          <div className="space-y-2">
                            <Label htmlFor="api-key-env">API Key 环境变量</Label>
                            <Input
                              id="api-key-env"
                              aria-label="API Key 环境变量"
                              value={selectedProvider.api_key_env ?? ""}
                              onChange={(event) =>
                                updateSelectedProvider((provider) => ({
                                  ...provider,
                                  api_key_env: event.target.value,
                                }))
                              }
                            />
                          </div>
                          <div className="space-y-2">
                            <Label htmlFor="api-key">API Key</Label>
                            <Input
                              id="api-key"
                              aria-label="API Key"
                              type="password"
                              value={selectedProvider.api_key ?? ""}
                              placeholder={
                                selectedProvider.has_api_key
                                  ? "已保存，留空则保持不变"
                                  : "输入新的 API Key"
                              }
                              onChange={(event) =>
                                updateSelectedProvider((provider) => ({
                                  ...provider,
                                  api_key: event.target.value,
                                }))
                              }
                            />
                          </div>
                        </div>

                        <div className="space-y-2">
                          <Label htmlFor="models-text">模型列表</Label>
                          <Textarea
                            id="models-text"
                            aria-label="模型列表"
                            value={selectedProvider.models_text ?? ""}
                            placeholder="每行一个模型，或使用逗号分隔"
                            rows={5}
                            onChange={(event) =>
                              updateSelectedProvider((provider) => ({
                                ...provider,
                                models_text: event.target.value,
                              }))
                            }
                          />
                          <div className="text-xs text-muted-foreground">
                            当前解析到 {parseModelsText(selectedProvider.models_text ?? "").length} 个模型
                          </div>
                        </div>

                        <div className="space-y-2">
                          <Label htmlFor="test-model">测试模型</Label>
                          <Input
                            id="test-model"
                            aria-label="测试模型"
                            value={
                              selectedProvider.test_model ??
                              parseModelsText(selectedProvider.models_text ?? "")[0] ??
                              ""
                            }
                            onChange={(event) =>
                              updateSelectedProvider((provider) => ({
                                ...provider,
                                test_model: event.target.value,
                              }))
                            }
                          />
                        </div>

                        <div className="flex justify-end">
                          <Button
                            type="button"
                            variant="outline"
                            disabled={testing}
                            onClick={handleTest}
                          >
                            测试连接
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
