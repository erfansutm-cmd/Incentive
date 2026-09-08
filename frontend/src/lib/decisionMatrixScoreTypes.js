// Database identifiers and UI captions are deliberately separate. Custom names
// are preserved; only these three presets have a fixed storage/display mapping.
export const scoreTypeOptions = [
  { value: 'performance', label: 'Performance' },
  { value: 'weather', label: 'Weather' },
  { value: 'order_level_increase', label: 'Order Level Increase' },
]

function preset(value) {
  const name = String(value ?? '').trim().toLowerCase()
  return scoreTypeOptions.find((option) => option.value === name || option.label.toLowerCase() === name)
}

export function scoreTypeValue(value) {
  return preset(value)?.value ?? String(value ?? '').trim()
}

export function scoreTypeLabel(value) {
  return preset(value)?.label ?? String(value ?? '').trim()
}
