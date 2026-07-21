<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'

const emit = defineEmits<{ close: [] }>()

const provider = ref('anthropic')
const model = ref('')
const baseUrl = ref('')
const apiKey = ref('')
const masked = ref('')
const saving = ref(false)
const msg = ref('')

onMounted(async () => {
  const s = await api.getLLMSettings()
  provider.value = s.provider
  model.value = s.model
  baseUrl.value = s.base_url
  masked.value = s.api_key_masked
})

async function save() {
  saving.value = true
  msg.value = ''
  try {
    const s = await api.saveLLMSettings({
      provider: provider.value, model: model.value,
      base_url: baseUrl.value, api_key: apiKey.value,
    })
    masked.value = s.api_key_masked
    apiKey.value = ''
    msg.value = '已保存'
  } catch (e: any) {
    msg.value = e.message
  } finally {
    saving.value = false
  }
}

const presets: Record<string, { model: string; base_url: string }> = {
  anthropic: { model: 'claude-opus-4-8', base_url: '' },
  openai_compat: { model: 'deepseek-chat', base_url: 'https://api.deepseek.com/v1' },
}

function applyPreset() {
  model.value = presets[provider.value].model
  baseUrl.value = presets[provider.value].base_url
}
</script>

<template>
  <div class="mask" @click.self="emit('close')">
    <div class="dialog">
      <h3>LLM 设置</h3>
      <p class="tip">测试阶段由用户自带 API Key; Key 保存在服务端, 不会回传明文。</p>

      <label>服务商</label>
      <select v-model="provider" @change="applyPreset">
        <option value="anthropic">Anthropic (Claude)</option>
        <option value="openai_compat">OpenAI 兼容 (DeepSeek/Qwen/GLM…)</option>
      </select>

      <label>模型</label>
      <input v-model="model" placeholder="如 claude-opus-4-8 / deepseek-chat" />

      <label>Base URL <span class="opt">(Anthropic 官方可留空)</span></label>
      <input v-model="baseUrl" placeholder="如 https://api.deepseek.com/v1" />

      <label>API Key <span class="opt">{{ masked ? `当前: ${masked}, 留空保持不变` : '' }}</span></label>
      <input v-model="apiKey" type="password" placeholder="sk-…" />

      <div class="btns">
        <span class="msg">{{ msg }}</span>
        <button class="ghost" @click="emit('close')">关闭</button>
        <button :disabled="saving" @click="save">保存</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mask {
  position: fixed; inset: 0; background: rgba(0,0,0,0.35);
  display: flex; align-items: center; justify-content: center; z-index: 50;
}
.dialog {
  background: #fff; border-radius: 10px; padding: 22px 26px; width: 440px;
  display: flex; flex-direction: column; gap: 6px;
}
h3 { margin: 0 0 4px; }
.tip { font-size: 12px; color: #888; margin: 0 0 8px; }
label { font-size: 13px; color: #444; margin-top: 6px; }
.opt { color: #999; font-weight: normal; font-size: 12px; }
input, select { padding: 7px 10px; border: 1px solid #ccd6e0; border-radius: 6px; font-size: 13px; }
.btns { display: flex; gap: 8px; justify-content: flex-end; align-items: center; margin-top: 14px; }
.msg { margin-right: auto; font-size: 12px; color: #27ae60; }
button {
  background: #2c7be5; color: #fff; border: 0; border-radius: 6px;
  padding: 7px 18px; cursor: pointer;
}
button.ghost { background: #fff; color: #555; border: 1px solid #ccd6e0; }
</style>
