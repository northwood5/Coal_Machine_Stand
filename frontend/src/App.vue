<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from './api'
import type { Design, DesignDetail, ModuleInfo, ModuleRunResult, Project } from './api'
import AgentPanel from './components/AgentPanel.vue'
import ModuleTree from './components/ModuleTree.vue'
import ParamForm from './components/ParamForm.vue'
import ResultView from './components/ResultView.vue'
import SettingsDialog from './components/SettingsDialog.vue'

const projects = ref<Project[]>([])
const designs = ref<Design[]>([])
const currentProjectId = ref<number | null>(null)
const currentDesign = ref<DesignDetail | null>(null)
const modules = ref<ModuleInfo[]>([])
const selectedModuleId = ref<string | null>(null)
const runResult = ref<ModuleRunResult | null>(null)
const running = ref(false)
const error = ref('')
const mode = ref<'classic' | 'agent'>('classic')
const showSettings = ref(false)

const selectedModule = computed(
  () => modules.value.find((m) => m.id === selectedModuleId.value) ?? null,
)

async function refreshProjects() {
  projects.value = await api.listProjects()
}

async function selectProject(id: number) {
  currentProjectId.value = id
  designs.value = await api.listDesigns(id)
  currentDesign.value = null
  modules.value = []
}

async function selectDesign(id: number) {
  currentDesign.value = await api.getDesign(id)
  modules.value = await api.listModules(id)
  runResult.value = null
}

async function refreshDesignState() {
  // Agent 工具改动数据模型后, 双模式共享状态在此同步
  if (!currentDesign.value) return
  currentDesign.value = await api.getDesign(currentDesign.value.id)
  modules.value = await api.listModules(currentDesign.value.id)
}

async function newProject() {
  const name = prompt('项目名称:')
  if (!name) return
  const p = await api.createProject(name)
  await refreshProjects()
  await selectProject(p.id)
}

async function newDesign() {
  if (currentProjectId.value === null) return
  const name = prompt('方案名称:')
  if (!name) return
  const d = await api.createDesign(currentProjectId.value, name)
  designs.value = await api.listDesigns(currentProjectId.value)
  await selectDesign(d.id)
}

async function saveParams(section: string, values: Record<string, any>) {
  if (!currentDesign.value) return
  error.value = ''
  try {
    currentDesign.value = await api.updateParams(currentDesign.value.id, section, values)
    modules.value = await api.listModules(currentDesign.value.id)
  } catch (e: any) {
    error.value = e.message
  }
}

async function runModule(moduleId: string) {
  if (!currentDesign.value) return
  running.value = true
  error.value = ''
  try {
    runResult.value = await api.runModule(currentDesign.value.id, moduleId)
    await refreshDesignState()
  } catch (e: any) {
    error.value = e.message
  } finally {
    running.value = false
  }
}

function openReport() {
  if (currentDesign.value) window.open(api.reportUrl(currentDesign.value.id), '_blank')
}

onMounted(refreshProjects)
</script>

<template>
  <div class="layout">
    <header>
      <span class="title">液压支架总体设计</span>
      <select
        :value="currentProjectId ?? ''"
        @change="selectProject(Number(($event.target as HTMLSelectElement).value))"
      >
        <option value="" disabled>选择项目…</option>
        <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }}</option>
      </select>
      <button @click="newProject">+ 项目</button>
      <select
        :value="currentDesign?.id ?? ''"
        :disabled="currentProjectId === null"
        @change="selectDesign(Number(($event.target as HTMLSelectElement).value))"
      >
        <option value="" disabled>选择方案…</option>
        <option v-for="d in designs" :key="d.id" :value="d.id">{{ d.name }}</option>
      </select>
      <button :disabled="currentProjectId === null" @click="newDesign">+ 方案</button>

      <div class="spacer" />
      <div class="mode-switch">
        <button :class="{ on: mode === 'classic' }" @click="mode = 'classic'">传统模式</button>
        <button :class="{ on: mode === 'agent' }" @click="mode = 'agent'">Agent 模式</button>
      </div>
      <button :disabled="!currentDesign" @click="openReport">📄 报告</button>
      <button @click="showSettings = true">⚙ LLM 设置</button>
    </header>

    <p v-if="error" class="error">{{ error }}</p>

    <main v-if="currentDesign">
      <!-- 传统模式: 模块树 / 表单 / 结果 -->
      <template v-if="mode === 'classic'">
        <aside class="left">
          <ModuleTree
            :modules="modules"
            :selected="selectedModuleId"
            @select="(id) => (selectedModuleId = id)"
          />
        </aside>
        <section class="center">
          <ParamForm
            :design="currentDesign"
            :module="selectedModule"
            @save="saveParams"
            @run="runModule"
          />
        </section>
        <aside class="right">
          <ResultView :result="runResult" :running="running" />
        </aside>
      </template>

      <!-- Agent 模式: 对话流 / 设计状态面板 -->
      <template v-else>
        <section class="center">
          <AgentPanel :design-id="currentDesign.id" @model-changed="refreshDesignState" />
        </section>
        <aside class="right wide">
          <ModuleTree :modules="modules" :selected="null" @select="() => {}" />
          <div class="state-summary">
            <h4>关键参数</h4>
            <table>
              <tr v-if="currentDesign.model.overall.height_min">
                <td>支撑高度</td>
                <td>{{ currentDesign.model.overall.height_min }} ~ {{ currentDesign.model.overall.height_max }} mm</td>
              </tr>
              <tr v-if="currentDesign.model.overall.working_resistance">
                <td>工作阻力</td><td>{{ currentDesign.model.overall.working_resistance }} kN</td>
              </tr>
              <tr v-if="currentDesign.model.linkage.rear_link_length">
                <td>后连杆</td><td>{{ currentDesign.model.linkage.rear_link_length }} mm</td>
              </tr>
              <tr v-if="currentDesign.model.loads && !currentDesign.model.loads.dirty">
                <td>载荷状态</td><td>✓ 有效 ({{ currentDesign.model.loads.cases.length }} 工况)</td>
              </tr>
            </table>
          </div>
        </aside>
      </template>
    </main>
    <p v-else class="empty">请选择或创建项目与方案</p>

    <SettingsDialog v-if="showSettings" @close="showSettings = false" />
  </div>
</template>

<style>
* { box-sizing: border-box; }
body { margin: 0; font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif; color: #2d3748; }
.layout { height: 100vh; display: flex; flex-direction: column; }
header {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 16px; background: #1f3a5f; color: #fff;
}
.title { font-weight: 700; margin-right: 12px; }
header select, header button {
  padding: 5px 10px; border-radius: 5px; border: 0; font-size: 13px; cursor: pointer;
}
.spacer { flex: 1; }
.mode-switch { display: flex; border-radius: 6px; overflow: hidden; }
.mode-switch button { border-radius: 0; background: #35507a; color: #cdd9ea; }
.mode-switch button.on { background: #fff; color: #1f3a5f; font-weight: 600; }
main { flex: 1; display: flex; min-height: 0; }
.left { width: 230px; border-right: 1px solid #e0e6ed; background: #fafbfc; }
.center { flex: 1; min-width: 0; }
.right { width: 340px; border-left: 1px solid #e0e6ed; background: #fafbfc; overflow-y: auto; }
.right.wide { width: 300px; }
.state-summary { padding: 0 12px 12px; font-size: 13px; }
.state-summary h4 { margin: 10px 0 6px; font-size: 13px; color: #555; }
.state-summary table { width: 100%; border-collapse: collapse; }
.state-summary td { border: 1px solid #eee; padding: 4px 8px; }
.error { color: #e74c3c; padding: 6px 16px; margin: 0; background: #fdeeee; font-size: 13px; }
.empty { text-align: center; color: #999; margin-top: 120px; }
</style>
