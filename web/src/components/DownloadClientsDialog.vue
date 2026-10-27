<template>
  <Teleport to="body">
    <div v-if="modelValue" class="dl-mask" @mousedown.self="close">
      <div class="dl-dialog" role="dialog" aria-modal="true" :aria-label="t('downloadClients.title')">
        <header class="dl-head">
          <div class="dl-head-text">
            <strong>{{ t('downloadClients.title') }}</strong>
            <span>{{ t('downloadClients.subtitle') }}</span>
          </div>
          <button type="button" class="dl-close" :aria-label="t('downloadClients.close')" @click="close">×</button>
        </header>

        <div class="dl-body">
          <section class="dl-pane">
            <div class="dl-pane-label">{{ t('downloadClients.desktop') }}</div>
            <h3>{{ t('downloadClients.desktopName') }}</h3>
            <p>{{ t('downloadClients.desktopDesc') }}</p>
            <button type="button" class="dl-btn dl-btn--primary" @click="onDesktopDownload">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                <path d="M12 3v12" stroke-linecap="round" />
                <path d="M8 11l4 4 4-4" stroke-linecap="round" stroke-linejoin="round" />
                <path d="M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2" stroke-linecap="round" />
              </svg>
              <span>{{ t('downloadClients.desktopCta') }}</span>
            </button>
            <span class="dl-meta">{{ t('downloadClients.desktopMeta') }}</span>
          </section>

          <div class="dl-divider" aria-hidden="true" />

          <section class="dl-pane">
            <div class="dl-pane-label">{{ t('downloadClients.mobile') }}</div>
            <h3>{{ t('downloadClients.mobileName') }}</h3>
            <p>{{ t('downloadClients.mobileDesc') }}</p>
            <div class="dl-qr-wrap">
              <img v-if="qrDataUrl" class="dl-qr" :src="qrDataUrl" :alt="t('downloadClients.qrAlt')" width="148" height="148" />
              <div v-else class="dl-qr dl-qr--placeholder" />
            </div>
            <span class="dl-meta">{{ t('downloadClients.mobileMeta') }}</span>
            <button type="button" class="dl-btn dl-btn--ghost" @click="onAndroidDownload">
              {{ t('downloadClients.mobileCta') }}
            </button>
          </section>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import QRCode from 'qrcode';
import { useI18n } from 'vue-i18n';
import {
  ANDROID_LANDING_URL,
  downloadAndroidApk,
  downloadGatewayClient,
} from '@/constants/downloads';

const props = defineProps<{ modelValue: boolean }>();
const emit = defineEmits<{ (e: 'update:modelValue', value: boolean): void }>();

const { t } = useI18n();
const qrDataUrl = ref('');

const close = () => emit('update:modelValue', false);

const onDesktopDownload = () => {
  downloadGatewayClient();
};

const onAndroidDownload = () => {
  downloadAndroidApk();
};

watch(
  () => props.modelValue,
  async (open) => {
    if (!open || qrDataUrl.value) return;
    try {
      qrDataUrl.value = await QRCode.toDataURL(ANDROID_LANDING_URL, {
        width: 296,
        margin: 1,
        color: { dark: '#111827', light: '#ffffff' },
        errorCorrectionLevel: 'M',
      });
    } catch {
      qrDataUrl.value = '';
    }
  },
);
</script>

<style scoped>
.dl-mask {
  position: fixed;
  inset: 0;
  z-index: 5000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.35);
  padding: 20px;
}

.dl-dialog {
  width: min(640px, calc(100vw - 32px));
  background: #fff;
  border-radius: 14px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.2);
  color: #111827;
  overflow: hidden;
}

.dl-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 18px 14px;
  border-bottom: 1px solid #eef0f2;
}

.dl-head-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.dl-head-text strong {
  font-size: 15px;
  font-weight: 600;
}

.dl-head-text span {
  font-size: 12px;
  color: #6b7280;
  line-height: 1.5;
}

.dl-close {
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 6px;
  background: transparent;
  font-size: 20px;
  line-height: 1;
  color: #6b7280;
  cursor: pointer;
  flex-shrink: 0;
}

.dl-close:hover {
  background: #f3f4f6;
}

.dl-body {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: stretch;
  padding: 8px 4px 8px;
}

.dl-pane {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 8px;
  padding: 20px 22px 22px;
}

.dl-pane-label {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #9ca3af;
}

.dl-pane h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

.dl-pane p {
  margin: 0 0 6px;
  font-size: 12px;
  line-height: 1.6;
  color: #6b7280;
  max-width: 220px;
}

.dl-divider {
  width: 1px;
  margin: 18px 0;
  background: #eef0f2;
}

.dl-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 36px;
  padding: 0 16px;
  border-radius: 8px;
  font-size: 13px;
  cursor: pointer;
  border: 1px solid #e5e7eb;
  background: #fff;
  color: #111827;
}

.dl-btn--primary {
  border-color: #111827;
  background: #111827;
  color: #fff;
}

.dl-btn--primary:hover {
  background: #000;
}

.dl-btn--ghost {
  margin-top: 2px;
  background: transparent;
  color: #6b7280;
}

.dl-btn--ghost:hover {
  background: #f3f4f6;
  color: #111827;
}

.dl-meta {
  font-size: 11px;
  color: #9ca3af;
  line-height: 1.5;
}

.dl-qr-wrap {
  margin: 4px 0 2px;
  padding: 10px;
  border: 1px solid #eef0f2;
  border-radius: 12px;
  background: #fafafa;
}

.dl-qr {
  display: block;
  width: 148px;
  height: 148px;
  border-radius: 4px;
}

.dl-qr--placeholder {
  background: linear-gradient(90deg, #f3f4f6 25%, #e5e7eb 50%, #f3f4f6 75%);
  background-size: 200% 100%;
  animation: dl-shimmer 1.2s ease infinite;
}

@keyframes dl-shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

@media (max-width: 560px) {
  .dl-body {
    grid-template-columns: 1fr;
  }

  .dl-divider {
    width: auto;
    height: 1px;
    margin: 0 22px;
  }

  .dl-pane p {
    max-width: none;
  }
}
</style>
