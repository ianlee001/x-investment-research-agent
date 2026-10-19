import type { ComponentProps } from 'react'
import { FieldError, Input, Label, ListBox, NumberField, SearchField, Select, TextArea, TextField } from '@heroui/react'

type FieldProps = Omit<ComponentProps<typeof TextField>, 'children'> & {
  label?: string; multiline?: boolean; rows?: number; placeholder?: string; autoFocus?: boolean
}

/** Shared composition, using HeroUI's value/validation and label/error association. */
export function Field({ label, multiline = false, rows = 3, placeholder, autoFocus, className = 'field', ...props }: FieldProps) {
  return <TextField {...props} fullWidth className={`app-field ${className}`}>
    {label && <Label>{label}{props.isRequired && <span className="required-indicator" aria-hidden="true"> *</span>}</Label>}
    {multiline ? <TextArea rows={rows} placeholder={placeholder} autoFocus={autoFocus} /> : <Input placeholder={placeholder} autoFocus={autoFocus} />}
    <FieldError />
  </TextField>
}

export function SearchInput({ label, value, onChange, placeholder, className = '' }: {
  label: string; value: string; onChange: (value: string) => void; placeholder?: string; className?: string
}) {
  return <SearchField aria-label={label} value={value} onChange={onChange} className={`app-search ${className}`} fullWidth>
    <SearchField.Group><SearchField.SearchIcon /><SearchField.Input placeholder={placeholder} /><SearchField.ClearButton aria-label={`清空${label}`} /></SearchField.Group>
  </SearchField>
}

type Option = { value: string; label: string }
export function SelectInput({ label, value, onChange, options, disabled, className = '', visibleLabel = false }: {
  label: string; value: string | number; onChange: (value: string) => void; options: Option[]; disabled?: boolean; className?: string; visibleLabel?: boolean
}) {
  // Prefix keys so the legitimate "all/new conversation" empty value is still a selectable item.
  return <Select fullWidth className={`app-select ${className}`} aria-label={visibleLabel ? undefined : label}
    value={`option:${value}`} onChange={key => { if (key != null) onChange(String(key).slice(7)) }} isDisabled={disabled}>
    {visibleLabel && <Label>{label}</Label>}
    <Select.Trigger><Select.Value /><Select.Indicator /></Select.Trigger>
    <Select.Popover className="app-select-popover"><ListBox aria-label={label}>
      {options.map(option => <ListBox.Item id={`option:${option.value}`} key={option.value} textValue={option.label}>
        {option.label}<ListBox.ItemIndicator />
      </ListBox.Item>)}
    </ListBox></Select.Popover>
  </Select>
}

export function NumberInput({ label, value, onChange, disabled, min = 0, max = 10 }: {
  label: string; value: number; onChange: (value: number) => void; disabled?: boolean; min?: number; max?: number
}) {
  return <NumberField className="app-number inline-field" value={value} onChange={next => { if (Number.isFinite(next)) onChange(next) }}
    isDisabled={disabled} minValue={min} maxValue={max} step={1}>
    <Label>{label}</Label><NumberField.Group>
      <NumberField.DecrementButton aria-label={`减少${label}`} /><NumberField.Input /><NumberField.IncrementButton aria-label={`增加${label}`} />
    </NumberField.Group><FieldError />
  </NumberField>
}
