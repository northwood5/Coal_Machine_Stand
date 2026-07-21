<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import type { DesignDetail, ModuleInfo } from '../api'

const props = defineProps<{
  design: DesignDetail
  module: ModuleInfo | null
}>()
const emit = defineEmits<{
  save: [section: string, values: Record<string, any>]
  run: [moduleId: string]
}>()

// 按区块分组当前模块的输入字段
const grouped = computed(() => {
  const groups: Record<string, { field: string; label: string; unit: string; required: boolean }[]> = {}
  for (const f of props.module?.input_fields ?? []) {
    const [section, field] = f.path.split('.')
    ;(groups[section] ??= []).push({ field, label: f.label, unit: f.unit, required: f.required })
  }
  return groups
})

// 本地编辑缓冲: section.field -> value
const buffer = reactive<Record<string, any>>({})

watch(
  () => [props.design, props.module] as const,
  () => {
    for (const key of Object.keys(buffer)) delete buffer[key]
    for (const [section, fields] of Object.entries(grouped.value)) {
      for (const f of fields) {
        const v = props.design.model[section]?.[f.field] ?? null
        buffer[`${section}.${f.field}`] = Array.isArray(v) ? v.join(', ') : v
      }
    }
  },
  { immediate: true, deep: false },
)

function parseValue(v: any): any {
  if (v === '' || v === null || v === undefined) return null
  if (typeof v !== 'string') return v
  // 铰点坐标: "x,y" → [x, y]
  if (v.includes(',')) {
    const parts = v.split(',').map((s) => Number(s.trim()))
    if (parts.every((n) => !Number.isNaN(n))) return parts
  }
  const n = Number(v)
  return Number.isNaN(n) ? v : n
}

function saveSection(section: string) {
  const values: Record<string, any> = {}
  for (const f of grouped.value[section] ?? []) {
    values[f.field] = parseValue(buffer[`${section}.${f.field}`])
  }
  emit('save', section, values)
}

const sectionNames: Record<string, string> = {
  meta: '基本信息',
  overall: '总体参数',
  linkage: '四连杆参数',
  sections: '截面参数',
}
</script>

<template>
  <div class="param-form">
    <template v-if="module">
      <div class="header">
        <h3>{{ module.name }} — 输入参数</h3>
        <button
          class="run-btn"
          :disabled="(module.missing_inputs?.length ?? 0) > 0"
          @click="emit('run', module.id)"
        >
          ▶ 运行计算
        </button>
      </div>
      <p v-if="module.missing_inputs?.length" class="warn">
        缺少 {{ module.missing_inputs.length }} 项必填参数，补齐后才能运行
      </p>

      <fieldset v-for="(fields, section) in grouped" :key="section">
        <legend>{{ sectionNames[section] ?? section }}</legend>
        <div v-for="f in fields" :key="f.field" class="row">
          <label :class="{ required: f.required }">{{ f.label }}</label>
          <input
            v-model="buffer[`${section}.${f.field}`]"
            :placeholder="f.unit ? `单位: ${f.unit}` : ''"
          />
          <span class="unit">{{ f.unit }}</span>
        </div>
        <button class="save-btn" @click="saveSection(section as string)">保存{{ sectionNames[section] ?? section }}</button>
      </fieldset>
    </template>
    <p v-else class="hint">请在左侧选择计算模块</p>
  </div>
</template>

<style scoped>
.param-form { padding: 16px; overflow-y: auto; }
.header { display: flex; justify-content: space-between; align-items: center; }
h3 { margin: 0; font-size: 16px; }
.run-btn {
  background: #2c7be5; color: #fff; border: 0; border-radius: 6px;
  padding: 8px 18px; cursor: pointer; font-size: 14px;
}
.run-btn:disabled { background: #b8c9dd; cursor: not-allowed; }
.warn { color: #e67e22; font-size: 13px; }
fieldset { border: 1px solid #e0e6ed; border-radius: 8px; margin: 14px 0; padding: 12px; }
legend { font-size: 13px; color: #666; padding: 0 6px; }
.row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
label { width: 160px; font-size: 13px; text-align: right; color: #444; }
label.required::after { content: ' *'; color: #e74c3c; }
input { flex: 1; padding: 6px 10px; border: 1px solid #ccd6e0; border-radius: 5px; font-size: 13px; }
.unit { width: 40px; font-size: 12px; color: #999; }
.save-btn {
  background: #fff; border: 1px solid #2c7be5; color: #2c7be5;
  border-radius: 5px; padding: 5px 14px; cursor: pointer; font-size: 12px;
}
.hint { color: #999; text-align: center; margin-top: 80px; }
</style>
