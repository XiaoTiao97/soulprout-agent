<template>
  <Teleport to="body">
    <div v-if="modelValue" class="ak-mask" @mousedown.self="close">
      <div class="ak-dialog" role="dialog" aria-modal="true" :aria-label="t('apiKeySettings.title')">
        <!-- 顶部标题与醒目提醒 -->
        <header class="ak-head">
          <div class="ak-head-bar">
            <strong>{{ t('apiKeySettings.title') }}</strong>
            <button type="button" class="ak-close" :aria-label="t('apiKeySettings.cancel')" @click="close">×</button>
          </div>
          <div class="ak-alert">
            <svg class="ak-alert-icon" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              <path fill-rule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 6a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 6zm0 9a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd" />
            </svg>
            <div class="ak-alert-text">
              <p>{{ t('apiKeySettings.alertLine1') }}</p>
              <p>{{ t('apiKeySettings.alertLine2') }}</p>
            </div>
          </div>
        </header>

        <div class="ak-body" :class="{ 'ak-body--loading': loading }">
          <!-- 1. 启用滑块（极简同行布局） -->
          <section class="ak-switch-row" @click="toggleEnable">
            <span class="ak-switch-title">{{ t('apiKeySettings.enableTitle') }}</span>
            <button
              type="button"
              role="switch"
              :aria-checked="form.use_custom_key"
              class="ak-toggle"
              :class="{ 'is-on': form.use_custom_key }"
              @click.stop="toggleEnable"
            >
              <span class="ak-toggle-knob"></span>
            </button>
          </section>

          <!-- 2. API Key 配置（选填） -->
          <section class="ak-section">
            <div class="ak-section-head">
              <h3>{{ t('apiKeySettings.keysSectionTitle') }}</h3>
            </div>

            <div class="ak-provider-panel">
              <div
                v-for="p in providers"
                :key="p.model_source"
                class="ak-provider-item"
                :class="{ 'is-configured': p.configured }"
              >
                <div class="ak-provider-main">
                  <div class="ak-provider-meta">
                    <span class="ak-status-dot" :class="{ 'is-on': p.configured }" aria-hidden="true"></span>
                    <span class="ak-provider-name">{{ p.display_name }}</span>
                    <span v-if="p.configured" class="ak-key-hint">{{ p.key_hint }}</span>
                  </div>

                  <div class="ak-provider-controls">
                    <input
                      v-model="keyInputs[p.model_source]"
                      type="password"
                      class="ak-input"
                      autocomplete="new-password"
                      spellcheck="false"
                      :placeholder="
                        p.configured
                          ? t('apiKeySettings.replaceKeyPlaceholder', { hint: p.key_hint })
                          : t('apiKeySettings.enterKeyPlaceholder', { name: p.display_name })
                      "
                      @keydown.enter.prevent="handleSaveSingleKey(p.model_source)"
                    />
                    <button
                      type="button"
                      class="ak-btn ak-btn--confirm"
                      :disabled="!keyInputs[p.model_source]?.trim() || savingSource === p.model_source"
                      @click="handleSaveSingleKey(p.model_source)"
                    >
                      {{
                        savingSource === p.model_source
                          ? t('apiKeySettings.savingKey')
                          : t('apiKeySettings.confirmKey')
                      }}
                    </button>
                    <button
                      v-if="p.configured"
                      type="button"
                      class="ak-btn-icon-del"
                      :title="t('apiKeySettings.deleteKey')"
                      :disabled="deletingSource === p.model_source"
                      @click="handleDeleteKey(p.model_source)"
                    >
                      {{ deletingSource === p.model_source ? '…' : t('apiKeySettings.deleteKey') }}
                    </button>
                  </div>
                </div>

                <!-- 豆包/火山方舟专属提示：生图与生视频工具说明 -->
                <div v-if="p.model_source === 'ark'" class="ak-ark-notice">
                  {{ t('apiKeySettings.arkMediaNotice') }}
                </div>
              </div>
            </div>
          </section>

          <!-- 3. 默认模型选择 -->
          <section class="ak-section">
            <div class="ak-section-head">
              <div class="ak-section-title-row">
                <h3>{{ t('apiKeySettings.modelsSectionTitle') }}</h3>
                <span class="ak-required-tag">{{ t('apiKeySettings.requiredTag') }}</span>
              </div>
              <span class="ak-section-hint">{{ t('apiKeySettings.modelsSectionHint') }}</span>
            </div>

            <div v-if="configuredModelOptions.length === 0" class="ak-empty-models">
              {{ t('apiKeySettings.noConfiguredProviderHint') }}
            </div>

            <div v-else class="ak-model-panel">
              <!-- 灵芽（Soulprout）模型 -->
              <div class="ak-model-row">
                <label class="ak-model-info" for="ak-soulprout-model">
                  <span class="ak-model-name">{{ t('apiKeySettings.soulproutModelLabel') }}</span>
                  <span class="ak-model-desc">{{ t('apiKeySettings.soulproutModelSub') }}</span>
                </label>
                <div class="ak-select-wrap">
                  <select
                    id="ak-soulprout-model"
                    v-model="soulproutCombined"
                    class="ak-select"
                  >
                    <option value="" disabled>{{ t('apiKeySettings.selectPlaceholder') }}</option>
                    <optgroup
                      v-for="group in configuredProviders"
                      :key="group.model_source"
                      :label="group.display_name"
                    >
                      <option
                        v-for="m in group.models"
                        :key="`${group.model_source}::${m}`"
                        :value="`${group.model_source}::${m}`"
                      >
                        {{ group.display_name }} · {{ m }}
                      </option>
                    </optgroup>
                  </select>
                </div>
              </div>

              <!-- Pro 模型 -->
              <div class="ak-model-row">
                <label class="ak-model-info" for="ak-pro-model">
                  <span class="ak-model-name">{{ t('apiKeySettings.proModelLabel') }}</span>
                  <span class="ak-model-desc">{{ t('apiKeySettings.proModelSub') }}</span>
                </label>
                <div class="ak-select-wrap">
                  <select
                    id="ak-pro-model"
                    v-model="proCombined"
                    class="ak-select"
                  >
                    <option value="" disabled>{{ t('apiKeySettings.selectPlaceholder') }}</option>
                    <optgroup
                      v-for="group in configuredProviders"
                      :key="group.model_source"
                      :label="group.display_name"
                    >
                      <option
                        v-for="m in group.models"
                        :key="`${group.model_source}::${m}`"
                        :value="`${group.model_source}::${m}`"
                      >
                        {{ group.display_name }} · {{ m }}
                      </option>
                    </optgroup>
                  </select>
                </div>
              </div>

              <!-- Flash 模型 -->
              <div class="ak-model-row">
                <label class="ak-model-info" for="ak-flash-model">
                  <span class="ak-model-name">{{ t('apiKeySettings.flashModelLabel') }}</span>
                  <span class="ak-model-desc">{{ t('apiKeySettings.flashModelSub') }}</span>
                </label>
                <div class="ak-select-wrap">
                  <select
                    id="ak-flash-model"
                    v-model="flashCombined"
                    class="ak-select"
                  >
                    <option value="" disabled>{{ t('apiKeySettings.selectPlaceholder') }}</option>
                    <optgroup
                      v-for="group in configuredProviders"
                      :key="group.model_source"
                      :label="group.display_name"
                    >
                      <option
                        v-for="m in group.models"
                        :key="`${group.model_source}::${m}`"
                        :value="`${group.model_source}::${m}`"
                      >
                        {{ group.display_name }} · {{ m }}
                      </option>
                    </optgroup>
                  </select>
                </div>
              </div>
            </div>
          </section>

          <p v-if="feedbackMsg" class="ak-feedback" :class="{ 'is-error': isError }">
            {{ feedbackMsg }}
          </p>
        </div>

        <footer class="ak-foot">
          <button type="button" class="ak-btn" @click="close">{{ t('apiKeySettings.cancel') }}</button>
          <button
            type="button"
            class="ak-btn ak-btn--primary"
            :disabled="savingPrefs || loading"
            @click="savePreferences"
          >
            {{ savingPrefs ? t('apiKeySettings.saving') : t('apiKeySettings.savePreferences') }}
          </button>
        </footer>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';
import axios from 'axios';
import { useI18n } from 'vue-i18n';

interface ProviderItem {
  model_source: string;
  display_name: string;
  models: string[];
  configured: boolean;
  key_hint: string;
  updated_at: string;
}

const props = defineProps<{ modelValue: boolean }>();
const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void;
  (e: 'updated'): void;
}>();

const { t } = useI18n();

const loading = ref(false);
const savingPrefs = ref(false);
const savingSource = ref('');
const deletingSource = ref('');
const feedbackMsg = ref('');
const isError = ref(false);

const providers = ref<ProviderItem[]>([]);
const keyInputs = reactive<Record<string, string>>({});

const form = reactive({
  use_custom_key: false,
  custom_soulprout_source: '',
  custom_soulprout_model: '',
  custom_pro_source: '',
  custom_pro_model: '',
  custom_flash_source: '',
  custom_flash_model: '',
});

const configuredProviders = computed(() =>
  providers.value.filter((p) => p.configured && p.models && p.models.length > 0),
);

const configuredModelOptions = computed(() => {
  const list: Array<{ source: string; model: string }> = [];
  for (const p of configuredProviders.value) {
    for (const m of p.models) {
      list.push({ source: p.model_source, model: m });
    }
  }
  return list;
});

function combineSourceModel(source: string, model: string): string {
  if (!source || !model) return '';
  return `${source}::${model}`;
}

function splitSourceModel(combined: string): { source: string; model: string } {
  if (!combined || !combined.includes('::')) return { source: '', model: '' };
  const [source, ...rest] = combined.split('::');
  return { source: source || '', model: rest.join('::') || '' };
}

const soulproutCombined = computed({
  get: () => combineSourceModel(form.custom_soulprout_source, form.custom_soulprout_model),
  set: (val: string) => {
    const { source, model } = splitSourceModel(val);
    form.custom_soulprout_source = source;
    form.custom_soulprout_model = model;
  },
});

const proCombined = computed({
  get: () => combineSourceModel(form.custom_pro_source, form.custom_pro_model),
  set: (val: string) => {
    const { source, model } = splitSourceModel(val);
    form.custom_pro_source = source;
    form.custom_pro_model = model;
  },
});

const flashCombined = computed({
  get: () => combineSourceModel(form.custom_flash_source, form.custom_flash_model),
  set: (val: string) => {
    const { source, model } = splitSourceModel(val);
    form.custom_flash_source = source;
    form.custom_flash_model = model;
  },
});

const showNotice = (msg: string, err = false) => {
  feedbackMsg.value = msg;
  isError.value = err;
};

const clearKeyInputs = () => {
  Object.keys(keyInputs).forEach((k) => {
    keyInputs[k] = '';
  });
};

const close = () => {
  clearKeyInputs();
  emit('update:modelValue', false);
};

const autoFillDefaultModelsIfNeeded = () => {
  const validSources = new Set(configuredProviders.value.map((p) => p.model_source));
  const firstProvider = configuredProviders.value[0];
  if (!firstProvider || firstProvider.models.length === 0) {
    form.custom_soulprout_source = '';
    form.custom_soulprout_model = '';
    form.custom_pro_source = '';
    form.custom_pro_model = '';
    form.custom_flash_source = '';
    form.custom_flash_model = '';
    return;
  }

  const defaultFlash =
    firstProvider.models.find((m) => m.includes('flash') || m.includes('lite')) ||
    firstProvider.models[0];
  const defaultPro =
    firstProvider.models.find((m) => m.includes('pro') && !m.includes('thinking')) ||
    firstProvider.models[0];

  if (!form.custom_soulprout_source || !validSources.has(form.custom_soulprout_source)) {
    form.custom_soulprout_source = firstProvider.model_source;
    form.custom_soulprout_model = defaultFlash;
  }
  if (!form.custom_pro_source || !validSources.has(form.custom_pro_source)) {
    form.custom_pro_source = firstProvider.model_source;
    form.custom_pro_model = defaultPro;
  }
  if (!form.custom_flash_source || !validSources.has(form.custom_flash_source)) {
    form.custom_flash_source = firstProvider.model_source;
    form.custom_flash_model = defaultFlash;
  }
};

const applyServerState = (data: Record<string, any>) => {
  providers.value = Array.isArray(data.providers) ? data.providers : [];
  form.use_custom_key = Boolean(data.use_custom_key);
  form.custom_soulprout_source = data.custom_soulprout_source || '';
  form.custom_soulprout_model = data.custom_soulprout_model || '';
  form.custom_pro_source = data.custom_pro_source || '';
  form.custom_pro_model = data.custom_pro_model || '';
  form.custom_flash_source = data.custom_flash_source || '';
  form.custom_flash_model = data.custom_flash_model || '';
  autoFillDefaultModelsIfNeeded();
};

const load = async () => {
  loading.value = true;
  showNotice('');
  clearKeyInputs();
  try {
    const res = await axios.get('/api/user/api-keys');
    if (res.data?.success) {
      applyServerState(res.data);
    } else {
      showNotice(res.data?.message || t('apiKeySettings.loadFailed'), true);
    }
  } catch {
    showNotice(t('apiKeySettings.loadFailed'), true);
  } finally {
    loading.value = false;
  }
};

const toggleEnable = () => {
  if (!form.use_custom_key && configuredProviders.value.length === 0) {
    showNotice(t('apiKeySettings.needKeyBeforeEnable'), true);
    return;
  }
  form.use_custom_key = !form.use_custom_key;
  if (form.use_custom_key) {
    autoFillDefaultModelsIfNeeded();
  }
  showNotice('');
};

const handleSaveSingleKey = async (modelSource: string) => {
  const raw = (keyInputs[modelSource] || '').trim();
  if (!raw) return;

  savingSource.value = modelSource;
  showNotice('');
  try {
    const res = await axios.post('/api/user/api-keys/key', {
      model_source: modelSource,
      api_key: raw,
    });
    keyInputs[modelSource] = '';
    if (res.data?.success) {
      applyServerState(res.data);
      showNotice(res.data?.message || t('apiKeySettings.keySavedSuccess'), false);
      emit('updated');
    } else {
      showNotice(res.data?.message || t('apiKeySettings.saveFailed'), true);
    }
  } catch {
    keyInputs[modelSource] = '';
    showNotice(t('apiKeySettings.saveFailed'), true);
  } finally {
    savingSource.value = '';
  }
};

const handleDeleteKey = async (modelSource: string) => {
  deletingSource.value = modelSource;
  showNotice('');
  try {
    const res = await axios.delete(`/api/user/api-keys/key/${encodeURIComponent(modelSource)}`);
    if (res.data?.success) {
      applyServerState(res.data);
      showNotice(res.data?.message || t('apiKeySettings.keyDeletedSuccess'), false);
      emit('updated');
    } else {
      showNotice(res.data?.message || t('apiKeySettings.saveFailed'), true);
    }
  } catch {
    showNotice(t('apiKeySettings.saveFailed'), true);
  } finally {
    deletingSource.value = '';
  }
};

const savePreferences = async () => {
  if (form.use_custom_key) {
    if (configuredProviders.value.length === 0) {
      showNotice(t('apiKeySettings.needKeyBeforeEnable'), true);
      return;
    }
    if (
      !form.custom_soulprout_source ||
      !form.custom_soulprout_model ||
      !form.custom_pro_source ||
      !form.custom_pro_model ||
      !form.custom_flash_source ||
      !form.custom_flash_model
    ) {
      showNotice(t('apiKeySettings.allThreeModelsRequired'), true);
      return;
    }
  }

  savingPrefs.value = true;
  showNotice('');
  try {
    const res = await axios.put('/api/user/api-keys/preferences', {
      use_custom_key: form.use_custom_key,
      custom_soulprout_source: form.custom_soulprout_source || null,
      custom_soulprout_model: form.custom_soulprout_model || null,
      custom_pro_source: form.custom_pro_source || null,
      custom_pro_model: form.custom_pro_model || null,
      custom_flash_source: form.custom_flash_source || null,
      custom_flash_model: form.custom_flash_model || null,
    });
    if (res.data?.success) {
      applyServerState(res.data);
      emit('updated');
      close();
    } else {
      showNotice(res.data?.message || t('apiKeySettings.saveFailed'), true);
    }
  } catch {
    showNotice(t('apiKeySettings.saveFailed'), true);
  } finally {
    savingPrefs.value = false;
  }
};

watch(
  () => props.modelValue,
  (open) => {
    if (open) load();
    else clearKeyInputs();
  },
);
</script>

<style scoped>
/* ─── 遮罩与弹窗骨架（对齐 PersonalizeDialog / DownloadClientsDialog） ─── */
.ak-mask {
  position: fixed;
  inset: 0;
  z-index: 5000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.35);
  backdrop-filter: blur(2px);
  padding: 16px;
}

.ak-dialog {
  display: flex;
  flex-direction: column;
  width: min(560px, calc(100vw - 32px));
  max-height: calc(100vh - 48px);
  background: #ffffff;
  border-radius: 14px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.2);
  color: #111827;
  box-sizing: border-box;
  overflow: hidden;
}

/* ─── 头部与鲜明风险提醒 ─── */
.ak-head {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 15px 18px 14px;
  border-bottom: 1px solid #eef0f2;
}

.ak-head-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.ak-head-bar strong {
  font-size: 15px;
  font-weight: 600;
  letter-spacing: -0.01em;
}

.ak-close {
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 6px;
  background: transparent;
  font-size: 20px;
  line-height: 1;
  color: #6b7280;
  cursor: pointer;
  transition: background-color 0.15s ease, color 0.15s ease;
}

.ak-close:hover {
  background: #f3f4f6;
  color: #111827;
}

.ak-alert {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  padding: 9px 12px;
  border-radius: 9px;
  background: #fff7ed;
  border: 1px solid #fed7aa;
  color: #c2410c;
}

.ak-alert-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  margin-top: 2px;
  color: #ea580c;
}

.ak-alert-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 12px;
  font-weight: 500;
  line-height: 1.5;
}

.ak-alert-text p {
  margin: 0;
}

/* ─── 内容滚动区 ─── */
.ak-body {
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 16px 18px;
  overflow-y: auto;
}

.ak-body--loading {
  opacity: 0.5;
  pointer-events: none;
}

/* ─── 1. 启用开关行（克制干净的卡片条） ─── */
.ak-switch-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 11px 14px;
  background: #f9fafb;
  border: 1px solid #eef0f2;
  border-radius: 10px;
  cursor: pointer;
  user-select: none;
  transition: border-color 0.15s ease;
}

.ak-switch-row:hover {
  border-color: #e5e7eb;
}

.ak-switch-title {
  font-size: 13.5px;
  font-weight: 600;
  color: #111827;
}

.ak-toggle {
  position: relative;
  width: 40px;
  height: 22px;
  flex-shrink: 0;
  border: none;
  border-radius: 999px;
  background: #d1d5db;
  cursor: pointer;
  padding: 2px;
  transition: background-color 0.22s cubic-bezier(0.4, 0, 0.2, 1);
}

.ak-toggle.is-on {
  background: #111827;
}

.ak-toggle-knob {
  display: block;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #ffffff;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
  transition: transform 0.22s cubic-bezier(0.4, 0, 0.2, 1);
}

.ak-toggle.is-on .ak-toggle-knob {
  transform: translateX(18px);
}

/* ─── 分组标题 ─── */
.ak-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ak-section-head {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.ak-section-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.ak-section-head h3 {
  margin: 0;
  font-size: 13.5px;
  font-weight: 600;
  color: #111827;
}

.ak-section-hint {
  font-size: 12px;
  color: #6b7280;
  line-height: 1.45;
}

.ak-required-tag {
  font-size: 11px;
  font-weight: 500;
  padding: 1px 7px;
  border-radius: 999px;
  background: #f3f4f6;
  color: #4b5563;
}

/* ─── 2. 平台 Key 列表（一体化分组面板，去除琐碎边框与廉价胶囊） ─── */
.ak-provider-panel {
  display: flex;
  flex-direction: column;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  background: #ffffff;
  overflow: hidden;
}

.ak-provider-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 9px 12px;
  border-bottom: 1px solid #f3f4f6;
  transition: background-color 0.15s ease;
}

.ak-provider-item:last-child {
  border-bottom: none;
}

.ak-provider-item:hover {
  background: #fafafa;
}

.ak-provider-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.ak-provider-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 145px;
  flex-shrink: 0;
}

.ak-status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #d1d5db;
  flex-shrink: 0;
}

.ak-status-dot.is-on {
  background: #16a34a;
  box-shadow: 0 0 0 3px rgba(22, 163, 74, 0.12);
}

.ak-provider-name {
  font-size: 13px;
  font-weight: 500;
  color: #111827;
}

.ak-key-hint {
  font-size: 11px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  color: #6b7280;
  background: #f3f4f6;
  padding: 1px 6px;
  border-radius: 4px;
}

.ak-provider-controls {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
  min-width: 0;
}

.ak-input {
  flex: 1;
  min-width: 0;
  height: 32px;
  padding: 0 10px;
  border: 1px solid #e5e7eb;
  border-radius: 7px;
  background: #ffffff;
  font: inherit;
  font-size: 12.5px;
  color: #111827;
  box-sizing: border-box;
  outline: none;
  transition: border-color 0.15s ease;
}

.ak-input::placeholder {
  color: #9ca3af;
}

.ak-input:focus {
  border-color: #9ca3af;
}

.ak-btn-icon-del {
  height: 32px;
  padding: 0 8px;
  border: none;
  border-radius: 7px;
  background: transparent;
  font-size: 12px;
  color: #9ca3af;
  cursor: pointer;
  flex-shrink: 0;
  transition: color 0.15s ease, background-color 0.15s ease;
}

.ak-btn-icon-del:hover:not(:disabled) {
  color: #b91c1c;
  background: rgba(185, 28, 28, 0.06);
}

.ak-ark-notice {
  margin-left: 14px;
  font-size: 11.5px;
  line-height: 1.45;
  color: #6b7280;
}

/* ─── 3. 默认模型面板（左标题说明 + 右下拉框，对齐设置页质感） ─── */
.ak-empty-models {
  padding: 16px 12px;
  border: 1px dashed #e5e7eb;
  border-radius: 10px;
  font-size: 12.5px;
  color: #9ca3af;
  text-align: center;
  background: #fafafa;
}

.ak-model-panel {
  display: flex;
  flex-direction: column;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  background: #ffffff;
  overflow: hidden;
}

.ak-model-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 10px 12px;
  border-bottom: 1px solid #f3f4f6;
}

.ak-model-row:last-child {
  border-bottom: none;
}

.ak-model-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
}

.ak-model-name {
  font-size: 13px;
  font-weight: 500;
  color: #111827;
}

.ak-model-desc {
  font-size: 11.5px;
  color: #6b7280;
}

.ak-select-wrap {
  width: 220px;
  flex-shrink: 0;
}

.ak-select {
  width: 100%;
  height: 32px;
  padding: 0 8px;
  border: 1px solid #e5e7eb;
  border-radius: 7px;
  background: #ffffff;
  font: inherit;
  font-size: 12.5px;
  color: #111827;
  outline: none;
  cursor: pointer;
  transition: border-color 0.15s ease;
}

.ak-select:focus {
  border-color: #9ca3af;
}

/* ─── 反馈与底部按钮（严格对齐 PersonalizeDialog） ─── */
.ak-feedback {
  margin: 0;
  font-size: 12px;
  color: #15803d;
}

.ak-feedback.is-error {
  color: #b91c1c;
}

.ak-foot {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 18px;
  border-top: 1px solid #eef0f2;
}

.ak-btn {
  padding: 6px 16px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #ffffff;
  font-size: 13px;
  color: #111827;
  cursor: pointer;
  white-space: nowrap;
  transition: background-color 0.15s ease, border-color 0.15s ease;
}

.ak-btn:hover:not(:disabled) {
  background: #f3f4f6;
}

.ak-btn--confirm {
  height: 32px;
  padding: 0 12px;
  font-size: 12.5px;
  font-weight: 500;
  background: #111827;
  border-color: #111827;
  color: #ffffff;
  border-radius: 7px;
}

.ak-btn--confirm:hover:not(:disabled) {
  background: #000000;
}

.ak-btn--primary {
  border-color: #111827;
  background: #111827;
  color: #ffffff;
}

.ak-btn--primary:hover:not(:disabled) {
  background: #000000;
}

.ak-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

@media (max-width: 520px) {
  .ak-provider-main,
  .ak-model-row {
    flex-direction: column;
    align-items: stretch;
    gap: 8px;
  }

  .ak-select-wrap {
    width: 100%;
  }
}

/* ─── Dark Mode（严格对齐 PersonalizeDialog 暗色规范） ─── */
html[data-theme='dark'] .ak-mask {
  background: rgba(0, 0, 0, 0.65);
}

html[data-theme='dark'] .ak-dialog {
  background: #242424;
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: #f5f5f5;
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.55);
}

html[data-theme='dark'] .ak-head,
html[data-theme='dark'] .ak-foot {
  border-color: rgba(255, 255, 255, 0.08);
}

html[data-theme='dark'] .ak-close {
  color: #a3a3a3;
}

html[data-theme='dark'] .ak-close:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #f5f5f5;
}

html[data-theme='dark'] .ak-alert {
  background: rgba(234, 88, 12, 0.12);
  border-color: rgba(251, 146, 60, 0.3);
  color: #fdba74;
}

html[data-theme='dark'] .ak-alert-icon {
  color: #fb923c;
}

html[data-theme='dark'] .ak-switch-row {
  background: #1c1c1c;
  border-color: rgba(255, 255, 255, 0.08);
}

html[data-theme='dark'] .ak-switch-title,
html[data-theme='dark'] .ak-section-head h3,
html[data-theme='dark'] .ak-provider-name,
html[data-theme='dark'] .ak-model-name {
  color: #f5f5f5;
}

html[data-theme='dark'] .ak-toggle {
  background: #404040;
}

html[data-theme='dark'] .ak-toggle.is-on {
  background: #f5f5f5;
}

html[data-theme='dark'] .ak-toggle.is-on .ak-toggle-knob {
  background: #171717;
}

html[data-theme='dark'] .ak-section-hint,
html[data-theme='dark'] .ak-model-desc,
html[data-theme='dark'] .ak-ark-notice {
  color: #a3a3a3;
}

html[data-theme='dark'] .ak-required-tag,
html[data-theme='dark'] .ak-key-hint {
  background: #2e2e2e;
  color: #a3a3a3;
}

html[data-theme='dark'] .ak-provider-panel,
html[data-theme='dark'] .ak-model-panel {
  background: #1c1c1c;
  border-color: rgba(255, 255, 255, 0.09);
}

html[data-theme='dark'] .ak-provider-item,
html[data-theme='dark'] .ak-model-row {
  border-bottom-color: rgba(255, 255, 255, 0.06);
}

html[data-theme='dark'] .ak-provider-item:hover {
  background: rgba(255, 255, 255, 0.03);
}

html[data-theme='dark'] .ak-empty-models {
  background: #1c1c1c;
  border-color: rgba(255, 255, 255, 0.1);
  color: #a3a3a3;
}

html[data-theme='dark'] .ak-input,
html[data-theme='dark'] .ak-select {
  background: #141414;
  border-color: rgba(255, 255, 255, 0.1);
  color: #f5f5f5;
}

html[data-theme='dark'] .ak-input:focus,
html[data-theme='dark'] .ak-select:focus {
  border-color: rgba(255, 255, 255, 0.25);
}

html[data-theme='dark'] .ak-btn {
  background: #2e2e2e;
  border-color: rgba(255, 255, 255, 0.1);
  color: #e5e5e5;
}

html[data-theme='dark'] .ak-btn:hover:not(:disabled) {
  background: #383838;
}

html[data-theme='dark'] .ak-btn--primary,
html[data-theme='dark'] .ak-btn--confirm {
  background: #f5f5f5;
  border-color: #f5f5f5;
  color: #171717;
}

html[data-theme='dark'] .ak-btn--primary:hover:not(:disabled),
html[data-theme='dark'] .ak-btn--confirm:hover:not(:disabled) {
  background: #ffffff;
}
</style>
