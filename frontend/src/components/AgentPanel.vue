<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { agentWebSocket, api } from '../api'
import type { AgentEvent } from '../api'

const props = defineProps<{ designId: number }>()
const emit = defineEmits<{ modelChanged: [] }>()

interface DisplayItem {
  kind: 'user' | 'assistant' | 'activity' | 'error'
  text: string
}

const items = ref<DisplayItem[]>([])
const input = ref('')
const busy = ref(false)
const configured = ref(true)
const chatBox = ref<HTMLElement | null>(null)
let ws: WebSocket | null = null

function scrollToEnd() {
  nextTick(() => chatBox.value?.scrollTo({ top: chatBox.value.scrollHeight }))
}

async function loadHistory() {
  items.value = []
  const hist = await api.getAgentHistory(props.designId)
  for (const m of hist) {
    if (m.role === 'user') items.value.push({ kind: 'user', text: m.content })
    else {
      if (m.content) items.value.push({ kind: 'assistant', text: m.content })
      if (m.tool_calls?.length)
        items.value.push({ kind: 'activity', text: `调用: ${m.tool_calls.join(', ')}` })
    }
  }
  scrollToEnd()
}

function connect() {
  ws?.close()
  ws = agentWebSocket(props.designId)
  ws.onmessage = (e) => {
    const ev: AgentEvent = JSON.parse(e.data)
    if (ev.type === 'text' && ev.content) {
      items.value.push({ kind: 'assistant', text: ev.content })
    } else if (ev.type === 'tool_call') {
      items.value.push({ kind: 'activity', text: `▶ ${ev.name}(${JSON.stringify(ev.arguments)})` })
    } else if (ev.type === 'tool_result') {
      items.value.push({ kind: 'activity', text: `✓ ${ev.name} 完成` })
      emit('modelChanged')          // 工具改了数据模型 → 通知刷新状态面板
    } else if (ev.type === 'done') {
      busy.value = false
    } else if (ev.type === 'error') {
      items.value.push({ kind: 'error', text: ev.message ?? '未知错误' })
      busy.value = false
      if (ev.message?.includes('API Key')) configured.value = false
    }
    scrollToEnd()
  }
  ws.onclose = () => { busy.value = false }
}

function send() {
  const text = input.value.trim()
  if (!text || busy.value || !ws || ws.readyState !== WebSocket.OPEN) return
  items.value.push({ kind: 'user', text })
  busy.value = true
  ws.send(JSON.stringify({ message: text }))
  input.value = ''
  scrollToEnd()
}

async function clearChat() {
  if (!confirm('清空对话历史?')) return
  await api.clearAgentHistory(props.designId)
  items.value = []
}

async function checkConfigured() {
  configured.value = (await api.getLLMSettings()).configured
}

watch(() => props.designId, () => { loadHistory(); connect() })
onMounted(() => { checkConfigured(); loadHistory(); connect() })
onUnmounted(() => ws?.close())
</script>

<template>
  <div class="agent-panel">
    <div class="toolbar">
      <span>Agent 对话</span>
      <button class="link" @click="clearChat">清空对话</button>
    </div>
    <p v-if="!configured" class="notice">
      尚未配置 LLM API Key —— 点击顶栏「⚙ LLM 设置」填写后即可对话
    </p>
    <div ref="chatBox" class="chat">
      <p v-if="items.length === 0" class="hint">
        试试: "帮我设计一个采高 2.4~5m、工作阻力 12000kN 的两柱掩护式支架"
      </p>
      <div v-for="(it, i) in items" :key="i" class="msg" :class="it.kind">
        <template v-if="it.kind === 'activity'">{{ it.text }}</template>
        <template v-else>{{ it.text }}</template>
      </div>
      <div v-if="busy" class="msg activity">思考中…</div>
    </div>
    <div class="input-row">
      <textarea
        v-model="input"
        rows="2"
        placeholder="描述设计需求, Enter 发送 (Shift+Enter 换行)"
        @keydown.enter.exact.prevent="send"
      />
      <button :disabled="busy || !input.trim()" @click="send">发送</button>
    </div>
  </div>
</template>

<style scoped>
.agent-panel { display: flex; flex-direction: column; height: 100%; }
.toolbar {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 14px; border-bottom: 1px solid #e0e6ed; font-weight: 600; font-size: 14px;
}
.link { background: none; border: none; color: #2c7be5; cursor: pointer; font-size: 12px; }
.notice { background: #fdf6ec; color: #8a5a00; margin: 0; padding: 8px 14px; font-size: 13px; }
.chat { flex: 1; overflow-y: auto; padding: 14px; display: flex; flex-direction: column; gap: 8px; }
.msg { max-width: 82%; padding: 8px 12px; border-radius: 10px; font-size: 14px; white-space: pre-wrap; }
.msg.user { align-self: flex-end; background: #2c7be5; color: #fff; }
.msg.assistant { align-self: flex-start; background: #f0f4f8; }
.msg.activity {
  align-self: flex-start; background: none; color: #999; font-size: 12px;
  font-family: Consolas, monospace; padding: 0 6px;
}
.msg.error { align-self: center; background: #fdeeee; color: #e74c3c; font-size: 13px; }
.hint { color: #999; text-align: center; margin-top: 40px; font-size: 13px; }
.input-row { display: flex; gap: 8px; padding: 10px 14px; border-top: 1px solid #e0e6ed; }
textarea {
  flex: 1; resize: none; border: 1px solid #ccd6e0; border-radius: 6px;
  padding: 8px 10px; font-size: 13px; font-family: inherit;
}
.input-row button {
  background: #2c7be5; color: #fff; border: 0; border-radius: 6px;
  padding: 0 20px; cursor: pointer;
}
.input-row button:disabled { background: #b8c9dd; cursor: not-allowed; }
</style>
