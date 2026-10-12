import { describe, expect, it } from 'vitest'

import { percent, prettyJson, score, shortHash, shortId, titleCase } from './format'

describe('format', () => {
  it('matches the Jinja pass-rate and score presentation', () => {
    expect(percent(1)).toBe('100%')
    expect(percent(0.666)).toBe('67%')
    expect(score(0.875)).toBe('0.875')
  })

  it('shortens identities without changing the original value', () => {
    expect(shortId('abcdefghijkl')).toBe('abcdefgh')
    expect(shortHash('a'.repeat(64))).toBe('aaaaaaaaaaaa')
    expect(titleCase('development')).toBe('Development')
    expect(titleCase('holdout')).toBe('Holdout')
  })

  it('serializes evidence as text rather than HTML', () => {
    expect(prettyJson({ script: "<script>alert('x')</script>" })).toContain(
      "<script>alert('x')</script>",
    )
  })
})
