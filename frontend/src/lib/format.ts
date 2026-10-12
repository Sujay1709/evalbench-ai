// Formatting matches the Jinja templates so both UIs report identical values.

export const percent = (value: number) => `${Math.round(value * 100)}%`

export const score = (value: number) => value.toFixed(3)

export const shortId = (value: string) => value.slice(0, 8)

export const shortHash = (value: string) => value.slice(0, 12)

export const titleCase = (value: string) =>
  value
    .replaceAll('_', ' ')
    .replace(/\w\S*/g, (word) => word[0].toUpperCase() + word.slice(1).toLowerCase())

export const measured = (value: number | null, digits = 2) =>
  value === null ? 'Unknown' : value.toFixed(digits)

export const timestamp = (value: string) =>
  `${new Date(value).toISOString().replace('T', ' ').slice(0, 16)} UTC`

export const prettyJson = (value: unknown) => JSON.stringify(value, null, 2)
