<template>
  <Teleport to="body">
    <div v-if="modelValue" class="pz-mask" @mousedown.self="close">
      <div class="pz-dialog" role="dialog" aria-modal="true" :aria-label="t('personalize.title')">
        <header class="pz-head">
          <strong>{{ t('personalize.title') }}</strong>
          <button type="button" class="pz-close" :aria-label="t('personalize.cancel')" @click="close">×</button>
        </header>

        <div class="pz-body" :class="{ 'pz-body--loading': loading }">
          <section class="pz-group">
            <h3>{{ t('personalize.userSection') }}</h3>
            <label class="pz-label" for="pz-username">{{ t('personalize.name') }}</label>
            <input
              id="pz-username"
              v-model="form.username"
              class="pz-input"
              maxlength="64"
              autocomplete="off"
              :placeholder="t('personalize.userNamePlaceholder')"
            />
            <label class="pz-label" for="pz-userinfo">{{ t('personalize.info') }}</label>
            <textarea
              id="pz-userinfo"
              v-model="form.userinfo"
              class="pz-textarea"
              rows="4"
              maxlength="1024"
              :placeholder="t('personalize.userInfoPlaceholder')"
            ></textarea>
            <span class="pz-count">{{ form.userinfo.length }} / 1024</span>
          </section>

          <section class="pz-group">
            <h3>{{ t('personalize.agentSection') }}</h3>
            <label class="pz-label" for="pz-agentname">{{ t('personalize.name') }}</label>
            <input
              id="pz-agentname"
              v-model="form.agentname"
              class="pz-input"
              maxlength="64"
              autocomplete="off"
              :placeholder="t('personalize.agentNamePlaceholder')"
            />
            <label class="pz-label" for="pz-agentinfo">{{ t('personalize.info') }}</label>
            <textarea
              id="pz-agentinfo"
              v-model="form.agentinfo"
              class="pz-textarea"
              rows="6"
              maxlength="1024"
              :placeholder="t('personalize.agentInfoPlaceholder')"
            ></textarea>
            <span class="pz-count">{{ form.agentinfo.length }} / 1024</span>
          </section>

          <p v-if="error" class="pz-error">{{ error }}</p>
        </div>

        <footer class="pz-foot">
          <button type="button" class="pz-btn" @click="close">{{ t('personalize.cancel') }}</button>
          <button type="button" class="pz-btn pz-btn--primary" :disabled="saving || loading" @click="save">
            {{ saving ? t('personalize.saving') : t('personalize.save') }}
          </button>
        </footer>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue';
import axios from 'axios';
import { useI18n } from 'vue-i18n';

const props = defineProps<{ modelValue: boolean }>();
const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void;
  (e: 'saved', profile: { username: string }): void;
}>();

const { t } = useI18n();

const form = reactive({
  username: '',
  userinfo: '',
  agentname: '',
  agentinfo: '',
});
const loading = ref(false);
const saving = ref(false);
const error = ref('');

const close = () => emit('update:modelValue', false);

const applyProfile = (data: Record<string, string>) => {
  form.username = data.username || '';
  form.userinfo = data.userinfo || '';
  form.agentname = data.agentname || '';
  form.agentinfo = data.agentinfo || '';
};

const load = async () => {
  loading.value = true;
  error.value = '';
  try {
    const res = await axios.get('/api/user/profile');
    if (res.data?.success) applyProfile(res.data);
    else error.value = res.data?.message || t('personalize.loadFailed');
  } catch {
    error.value = t('personalize.loadFailed');
  } finally {
    loading.value = false;
  }
};

const save = async () => {
  if (!form.username.trim() || !form.agentname.trim()) {
    error.value = t('personalize.nameRequired');
    return;
  }
  saving.value = true;
  error.value = '';
  try {
    const res = await axios.put('/api/user/profile', {
      username: form.username.trim(),
      userinfo: form.userinfo,
      agentname: form.agentname.trim(),
      agentinfo: form.agentinfo,
    });
    if (res.data?.success) {
      emit('saved', { username: res.data.username });
      close();
    } else {
      error.value = res.data?.message || t('personalize.saveFailed');
    }
  } catch {
    error.value = t('personalize.saveFailed');
  } finally {
    saving.value = false;
  }
};

watch(
  () => props.modelValue,
  (open) => {
    if (open) load();
  },
);
</script>

<style scoped>
.pz-mask {
  position: fixed;
  inset: 0;
  z-index: 5000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.35);
}

.pz-dialog {
  display: flex;
  flex-direction: column;
  width: min(520px, calc(100vw - 32px));
  max-height: calc(100vh - 64px);
  background: #fff;
  border-radius: 14px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.2);
  color: #111827;
  box-sizing: border-box;
}

.pz-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid #eef0f2;
  font-size: 15px;
}

.pz-close {
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 6px;
  background: transparent;
  font-size: 20px;
  line-height: 1;
  color: #6b7280;
  cursor: pointer;
}

.pz-close:hover {
  background: #f3f4f6;
}

.pz-body {
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 16px 18px;
  overflow-y: auto;
}

.pz-body--loading {
  opacity: 0.5;
  pointer-events: none;
}

.pz-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.pz-group h3 {
  margin: 0 0 2px;
  font-size: 14px;
  font-weight: 600;
}

.pz-label {
  font-size: 12px;
  color: #6b7280;
}

.pz-input,
.pz-textarea {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fff;
  font: inherit;
  font-size: 13px;
  color: #111827;
  box-sizing: border-box;
  outline: none;
  transition: border-color 0.15s ease;
}

.pz-textarea {
  resize: vertical;
  line-height: 1.5;
}

.pz-input:focus,
.pz-textarea:focus {
  border-color: #9ca3af;
}

.pz-count {
  align-self: flex-end;
  font-size: 11px;
  color: #9ca3af;
}

.pz-error {
  margin: 0;
  font-size: 12px;
  color: #b91c1c;
}

.pz-foot {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 18px;
  border-top: 1px solid #eef0f2;
}

.pz-btn {
  padding: 6px 16px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fff;
  font-size: 13px;
  color: #111827;
  cursor: pointer;
}

.pz-btn:hover {
  background: #f3f4f6;
}

.pz-btn--primary {
  border-color: #111827;
  background: #111827;
  color: #fff;
}

.pz-btn--primary:hover {
  background: #000;
}

.pz-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
