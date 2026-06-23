<!-- AgentMarket.vue - 智能体市场 -->
<template>
  <div class="agent-market">
    <div class="market-content">
      <div class="market-header">
        <img src="@/assets/images/agent_market.svg" alt="" class="market-icon" width="24" height="24" />
        <h3 class="market-title">{{ t('agentMarket.title') }}</h3>
      </div>
      <div v-if="marketLoading" class="market-loading">
        <div class="loading-spinner"></div>
        <p>{{ t('common.loading') }}</p>
      </div>
      <div v-else-if="marketError" class="market-error">
        <p>{{ marketError }}</p>
        <button class="retry-btn" @click="fetchMarketAgents">{{ t('common.retry') }}</button>
      </div>
      <div v-else-if="marketAgents.length === 0" class="market-empty">
        <p>{{ t('agentMarket.empty') }}</p>
      </div>
      <div v-else class="market-grid">
        <div
          v-for="agent in marketAgents"
          :key="agent.agent_id"
          class="market-card"
          @click="emit('viewDetail', agent, [...marketAgents])"
        >
          <div class="market-card-name">{{ agent.name_zh || agent.name }}</div>
          <div class="market-card-desc">{{ agent.description || t('common.noDescription') }}</div>
          <div class="market-card-by">{{ t('agentMarket.by') }}  {{ agent.user_name || t('common.unknown') }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import axios from 'axios'

const { t } = useI18n()

const emit = defineEmits<{ close: []; viewDetail: [agent: AgentCard, marketAgents: AgentCard[]] }>()

interface AgentCard {
  agent_id?: string
  user_id?: string
  name: string
  name_zh?: string | null
  description: string
  system_prompt: string
  tools?: string[]
  kbs?: string[]
  agents?: string[] | null
  model_source?: string
  model?: string
  user_name?: string
  public?: boolean
}

const marketAgents = ref<AgentCard[]>([])
const marketLoading = ref(false)
const marketError = ref('')

async function fetchMarketAgents() {
  marketLoading.value = true
  marketError.value = ''
  try {
    const res = await axios.get('/api/agent_cards_market')
    if (res.data && Array.isArray(res.data)) {
      marketAgents.value = res.data.map((item: any) => ({
        ...item,
        tools: item.tools || [],
        kbs: item.kbs || [],
        agents: item.agents || null
      }))
    } else if (res.data?.success === false) {
      marketError.value = res.data?.message || t('agentMarket.fetchFailed')
      marketAgents.value = []
    } else {
      marketAgents.value = []
    }
  } catch (err: any) {
    marketError.value = err?.response?.data?.message || t('agentMarket.loadFailed')
    marketAgents.value = []
  } finally {
    marketLoading.value = false
  }
}

onMounted(() => {
  fetchMarketAgents()
})
</script>

<style scoped>
.agent-market {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.market-content {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.market-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
  flex-shrink: 0;
}

.market-icon {
  opacity: 0.9;
}

.market-title {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 600;
  color: #1e293b;
}

.market-loading,
.market-error,
.market-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 48px;
  color: #64748b;
}

.market-error .retry-btn {
  padding: 8px 16px;
  background: #3b82f6;
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.9rem;
}

.market-error .retry-btn:hover {
  background: #2563eb;
}

.loading-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid #e2e8f0;
  border-top-color: #3b82f6;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.market-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  overflow-y: auto;
  padding-right: 8px;
}

.market-card {
  display: flex;
  flex-direction: column;
  padding: 16px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s;
  min-height: 140px;
}

.market-card:hover {
  border-color: #d1d5db;
  background: #f4f4f5;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.market-card-name {
  font-weight: 600;
  font-size: 1rem;
  color: #1e293b;
  margin-bottom: 8px;
  line-height: 1.3;
}

.market-card-desc {
  flex: 1;
  font-size: 0.8rem;
  color: #64748b;
  line-height: 1.4;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  line-clamp: 3;
  -webkit-box-orient: vertical;
}

.market-card-by {
  margin-top: 8px;
  font-size: 0.75rem;
  color: #94a3b8;
}

@media (max-width: 1200px) {
  .market-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (max-width: 768px) {
  .market-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
