import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import Badge from './Badge'

describe('Badge Component', () => {
  it('renders with correct text', () => {
    const { getByText } = render(<Badge>Test Badge</Badge>)
    expect(getByText('Test Badge')).toBeDefined()
  })

  it('applies info variant styles', () => {
    const { container } = render(<Badge variant="info">Info</Badge>)
    expect(container.firstChild).toBeDefined()
  })

  it('applies success variant styles', () => {
    const { container } = render(<Badge variant="success">Success</Badge>)
    expect(container.firstChild).toBeDefined()
  })

  it('renders with dot indicator when dot prop is true', () => {
    const { container } = render(<Badge dot>With Dot</Badge>)
    const dot = container.querySelector('.animate-pulse')
    expect(dot).toBeDefined()
  })
})