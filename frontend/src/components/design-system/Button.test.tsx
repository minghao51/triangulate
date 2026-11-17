import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import Button from './Button';

describe('Button', () => {
  it('applies scoped variant and size classes instead of unbuilt utilities', () => {
    const { container } = render(<Button variant="secondary" size="lg">Save</Button>);
    const el = container.querySelector('button')!;
    expect(el.className).toContain('ds-button');
    expect(el.className).toContain('ds-button--secondary');
    expect(el.className).toContain('ds-button--lg');
    expect(el.className).not.toContain('bg-[#');
    expect(el.className).not.toContain('px-4');
  });

  it('defaults to a non-submitting button type', () => {
    const { container } = render(<Button>Go</Button>);
    expect(container.querySelector('button')!.getAttribute('type')).toBe('button');
  });

  it('keeps native props, className, icon and children', () => {
    const { container } = render(
      <Button className="extra" icon={<span data-testid="icon">i</span>} aria-label="launch" title="t">
        Launch
      </Button>
    );
    const el = container.querySelector('button')!;
    expect(el.className).toContain('extra');
    expect(el.getAttribute('aria-label')).toBe('launch');
    expect(el.getAttribute('title')).toBe('t');
    expect(screen.getByTestId('icon')).toBeDefined();
    expect(el.textContent).toContain('Launch');
  });

  it('disables the control and marks busy while loading', () => {
    const { container } = render(<Button loading>Saving</Button>);
    const el = container.querySelector('button')!;
    expect(el.disabled).toBe(true);
    expect(el.getAttribute('aria-busy')).toBe('true');
    expect(el.className).toContain('ds-button--loading');
  });

  it('does not fire onClick when disabled and does when enabled', () => {
    const onClick = vi.fn();
    const { rerender } = render(
      <Button disabled onClick={onClick}>
        Run
      </Button>
    );
    fireEvent.click(screen.getByRole('button', { name: 'Run' }));
    expect(onClick).not.toHaveBeenCalled();

    rerender(<Button onClick={onClick}>Run</Button>);
    fireEvent.click(screen.getByRole('button', { name: 'Run' }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('is focusable by keyboard when not disabled', () => {
    render(<Button>Focus me</Button>);
    const button = screen.getByRole('button', { name: 'Focus me' }) as HTMLButtonElement;
    button.focus();
    expect(document.activeElement).toBe(button);
    expect(button.disabled).toBe(false);
  });
});
