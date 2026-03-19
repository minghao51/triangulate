# Phase 5: Polish & Integration - Implementation Plan

**Date**: 2025-03-19
**Status**: Ready for Implementation
**Bundle Target**: ~500KB (from current 609KB)
**Timeline**: 4 weeks

## Overview

This plan implements balanced improvements across animations, performance, accessibility, and UX for the Triangulate Intelligence Platform frontend. Focus on quick wins with incremental enhancements suitable for internal/demo use.

## Implementation Strategy

### Week 1-2: Animations + Performance (Visual Impact)

**Priority**: High - Immediate user-facing improvements

#### 1.1 Animation System Setup

**File**: `src/lib/animations.ts`

```typescript
// Animation presets and constants
export const ANIMATION_DURATION = {
  fast: 150,
  normal: 300,
  slow: 500,
} as const;

export const ANIMATION_EASING = {
  default: [0.25, 0.1, 0.25, 1], // ease-out
  bounce: [0.68, -0.55, 0.265, 1.55],
  smooth: [0.4, 0, 0.2, 1],
} as const;

export const pageTransition = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -10 },
  transition: { duration: ANIMATION_DURATION.normal, ease: ANIMATION_EASING.default }
};

export const staggerContainer = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: {
      staggerChildren: 0.05,
    }
  }
};

export const staggerItem = {
  hidden: { opacity: 0, y: 10 },
  show: { opacity: 1, y: 0 }
};
```

#### 1.2 Page Transitions

**File**: `src/components/PageTransition.tsx`

```typescript
import { motion } from 'framer-motion';
import { Outlet } from 'react-router-dom';
import { pageTransition } from '../lib/animations';

export const PageTransition: React.FC = () => {
  return (
    <motion.div
      initial="initial"
      animate="animate"
      exit="exit"
      variants={pageTransition}
    >
      <Outlet />
    </motion.div>
  );
};
```

**Update**: `src/App.tsx` - Wrap routes with PageTransition

#### 1.3 Enhanced Design System Components

**Files to Update**:
- `src/components/design-system/Button.tsx` - Add hover/active animations
- `src/components/design-system/Card.tsx` - Add hover lift effect
- `src/components/design-system/Badge.tsx` - Add scale on hover

**Button Animation Pattern**:
```typescript
const whileTap = { scale: 0.98 };
const whileHover = { scale: 1.02 };
```

#### 1.4 Staggered List Animations

**File**: `src/components/StaggeredList.tsx`

```typescript
import { motion } from 'framer-motion';
import { staggerContainer, staggerItem } from '../lib/animations';

interface StaggeredListProps {
  children: React.ReactNode;
  className?: string;
}

export const StaggeredList: React.FC<StaggeredListProps> = ({ children, className }) => {
  return (
    <motion.div
      variants={staggerContainer}
      initial="hidden"
      animate="show"
      className={className}
    >
      {React.Children.map(children, (child, i) => (
        <motion.div key={i} variants={staggerItem}>
          {child}
        </motion.div>
      ))}
    </motion.div>
  );
};
```

**Apply to**:
- `src/pages/Dashboard.tsx` - Metrics grid, recent cases
- `src/pages/CaseExplorer.tsx` - Case cards
- `src/pages/CaseIntelligenceCenter.tsx` - Tab panels

#### 1.5 Loading States

**File**: `src/components/LoadingSkeleton.tsx`

```typescript
import { motion } from 'framer-motion';

export const Skeleton: React.FC<{ className?: string }> = ({ className }) => {
  return (
    <motion.div
      className={`bg-[#1a1a1a] rounded-sm ${className}`}
      animate={{ opacity: [0.5, 1, 0.5] }}
      transition={{ duration: 1.5, repeat: Infinity, ease: "easeInOut" }}
    />
  );
};
```

#### 1.6 Code Splitting Implementation

**File**: `src/App.tsx`

```typescript
import { lazy, Suspense } from 'react';
import { LoadingSkeleton } from './components/LoadingSkeleton';

// Immediate load
import Dashboard from './pages/Dashboard';
import CaseExplorer from './pages/CaseExplorer';
import InvestigationComposer from './pages/InvestigationComposer';

// Lazy load - Case Intelligence Center + tabs
const CaseIntelligenceCenter = lazy(() => import('./pages/CaseIntelligenceCenter'));
const EvidenceTab = lazy(() => import('./pages/tabs/EvidenceTab'));
const ClaimsTab = lazy(() => import('./pages/tabs/ClaimsTab'));
const ExceptionsTab = lazy(() => import('./pages/tabs/ExceptionsTab'));
const PartiesTab = lazy(() => import('./pages/tabs/PartiesTab'));
const TimelineTab = lazy(() => import('./pages/tabs/TimelineTab'));
const ReportTab = lazy(() => import('./pages/tabs/ReportTab'));
const RunHistoryTab = lazy(() => import('./pages/tabs/RunHistoryTab'));

// Lazy load - Specialized views
const PipelineMonitor = lazy(() => import('./pages/PipelineMonitor'));
const CorroborationNetwork = lazy(() => import('./pages/CorroborationNetwork'));
const SourceAnalysis = lazy(() => import('./pages/SourceAnalysis'));
const NarrativeLandscape = lazy(() => import('./pages/NarrativeLandscape'));
const MonitoringCenter = lazy(() => import('./pages/MonitoringCenter'));

// Wrap lazy routes with Suspense
<Suspense fallback={<LoadingSkeleton className="h-screen" />}>
  <Route path="cases/:id/*" element={<CaseIntelligenceCenter />} />
  <Route path="cases/:id/pipeline" element={<PipelineMonitor />} />
  {/* ... other lazy routes */}
</Suspense>
```

**Vite Configuration**: Update `vite.config.ts` for manual chunks

```typescript
export default defineConfig({
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          'react-vendor': ['react', 'react-dom', 'react-router-dom'],
          'visualization': ['d3', 'reactflow'],
          'ui': ['framer-motion', 'lucide-react', 'clsx', 'tailwind-merge'],
        }
      }
    }
  }
});
```

### Week 3: Accessibility + Manual Refresh UX

**Priority**: High - Critical usability improvements

#### 2.1 Refresh Button Component

**File**: `src/components/RefreshButton.tsx`

```typescript
import { useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { motion } from 'framer-motion';

type RefreshState = 'idle' | 'refreshing' | 'success' | 'error';

export const RefreshButton: React.FC<{
  onRefresh: () => Promise<void>;
  lastUpdated?: Date;
}> = ({ onRefresh, lastUpdated }) => {
  const [state, setState] = useState<RefreshState>('idle');
  const [error, setError] = useState<string | null>(null);

  const handleRefresh = async () => {
    if (state === 'refreshing') return;

    setState('refreshing');
    setError(null);

    try {
      await onRefresh();
      setState('success');
      setTimeout(() => setState('idle'), 2000);
    } catch (err) {
      setState('error');
      setError(err instanceof Error ? err.message : 'Refresh failed');
      setTimeout(() => setState('idle'), 3000);
    }
  };

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={handleRefresh}
        className="p-2 hover:bg-[#1a1a1a] rounded-sm transition-colors"
        aria-label="Refresh data"
      >
        <motion.div
          animate={state === 'refreshing' ? { rotate: 360 } : { rotate: 0 }}
          transition={{ duration: 1, repeat: state === 'refreshing' ? Infinity : 0, ease: "linear" }}
        >
          <RefreshCw size={16} className={state === 'refreshing' ? 'text-[#00d4ff]' : 'text-[#9aa1b3]'} />
        </motion.div>
      </button>
      {lastUpdated && (
        <span className="text-xs text-[#6c7385]">
          Updated {formatRelativeTime(lastUpdated)}
        </span>
      )}
      {state === 'success' && (
        <span className="text-xs text-[#00ff9d]">Updated</span>
      )}
      {state === 'error' && (
        <span className="text-xs text-[#ff4757]">{error}</span>
      )}
    </div>
  );
};

function formatRelativeTime(date: Date): string {
  const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  return `${Math.floor(seconds / 3600)}h ago`;
}
```

#### 2.2 Add Refresh Controls to Pages

**Update Files**:
- `src/pages/Dashboard.tsx` - Add refresh button to header
- `src/pages/CaseIntelligenceCenter.tsx` - Add refresh button to each tab
- `src/pages/CorroborationNetwork.tsx` - Add refresh button
- `src/pages/SourceAnalysis.tsx` - Add refresh button

**Pattern**:
```typescript
// In page component
const { refetch } = useQuery({...});

<RefreshButton
  onRefresh={async () => { await refetch(); }}
  lastUpdated={data?.lastUpdated ? new Date(data.lastUpdated) : undefined}
/>
```

#### 2.3 Keyboard Navigation

**File**: `src/lib/keyboard-shortcuts.ts`

```typescript
export const keyboardShortcuts = {
  'Cmd+K': 'Focus search',
  'Cmd+R': 'Refresh current page',
  'Cmd+B': 'Toggle sidebar',
  'Escape': 'Close modal/dropdown',
  'ArrowDown': 'Next item',
  'ArrowUp': 'Previous item',
  'Enter': 'Select item',
} as const;

export function setupKeyboardShortcuts() {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Cmd+K to focus search
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        // Focus search input
      }

      // Escape to close modals
      if (e.key === 'Escape') {
        // Close active modal
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);
}
```

#### 2.4 Focus Management

**File**: `src/lib/focus-manager.ts`

```typescript
export function trapFocus(element: HTMLElement) {
  const focusableElements = element.querySelectorAll(
    'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
  );
  const firstElement = focusableElements[0] as HTMLElement;
  const lastElement = focusableElements[focusableElements.length - 1] as HTMLElement;

  const handleTab = (e: KeyboardEvent) => {
    if (e.key !== 'Tab') return;

    if (e.shiftKey) {
      if (document.activeElement === firstElement) {
        e.preventDefault();
        lastElement.focus();
      }
    } else {
      if (document.activeElement === lastElement) {
        e.preventDefault();
        firstElement.focus();
      }
    }
  };

  element.addEventListener('keydown', handleTab);
  firstElement?.focus();

  return () => element.removeEventListener('keydown', handleTab);
}

export function restoreFocus(savedElement: HTMLElement) {
  savedElement?.focus();
}
```

#### 2.5 ARIA Labels Enhancement

**Update Files**:
- `src/components/Layout/Shell.tsx` - Add ARIA labels to navigation
- `src/components/design-system/Button.tsx` - Ensure all buttons have labels
- `src/components/design-system/Badge.tsx` - Add aria-label for status

**Example**:
```typescript
<button
  aria-label="Refresh data"
  title="Refresh"
>
  <RefreshCw aria-hidden="true" />
</button>

<nav aria-label="Main navigation">
  <NavLink to="/dashboard" aria-label="Dashboard">
    <BarChart3 aria-hidden="true" />
  </NavLink>
</nav>
```

#### 2.6 Visible Focus Indicators

**File**: `src/index.css` - Add to existing styles

```css
/* Add to existing CSS */
*:focus-visible {
  outline: 2px solid #00d4ff;
  outline-offset: 2px;
}

button:focus-visible,
a:focus-visible,
input:focus-visible,
select:focus-visible {
  outline: 2px solid #00d4ff;
  outline-offset: 2px;
}
```

### Week 4: Documentation + Final Polish

**Priority**: Medium - Documentation and testing

#### 3.1 Architecture Documentation

**File**: `ARCHITECTURE.md`

```markdown
# Triangulate Frontend Architecture

## System Overview
The Triangulate Intelligence Platform is a React-based single-page application...

## Technology Stack
- React 19 + TypeScript + Vite
- React Router v7 for routing
- React Query for data fetching
- Zustand for state management
- Framer Motion for animations
- D3.js + React Flow for visualizations

## Directory Structure
```
src/
├── components/
│   ├── design-system/     # Reusable UI components
│   ├── data-visualization/ # Chart/graph components
│   ├── entities/          # Domain-specific components
│   └── Layout/            # Layout components
├── pages/                 # Route components
├── lib/                   # Utilities and helpers
├── stores/                # Zustand state stores
├── services/              # API services
└── types/                 # TypeScript types
```

## Data Flow
1. Component triggers data fetch via React Query
2. API service calls backend
3. Data cached in React Query
4. Zustand stores UI state
5. Components re-render on data changes

## State Management
- **Server State**: React Query (API data, caching, polling)
- **Client State**: Zustand (UI state, modals, notifications)
- **URL State**: React Router search params (filters, sorting)

## Performance Optimizations
- Code splitting with React.lazy()
- Manual chunks in Vite config
- Memoization with React.memo
- Lazy loading of visualizations

## Design System
See `COMPONENTS.md` for detailed component usage.
```

#### 3.2 Component Documentation

**File**: `COMPONENTS.md`

```markdown
# Design System Components

## Button
Primary action button with variants and states.

### Usage
\```tsx
import Button from './components/design-system/Button';

<Button variant="primary" size="md" onClick={handleClick}>
  Save Changes
</Button>
\```

### Props
- `variant`: 'primary' | 'secondary' | 'danger' | 'ghost'
- `size`: 'sm' | 'md' | 'lg'
- `loading`: boolean
- `icon`: React.ReactNode

## Card
Container component with header, body, footer.

### Usage
\```tsx
import Card, { CardHeader, CardTitle, CardBody } from './components/design-system/Card';

<Card hover>
  <CardHeader>
    <CardTitle>Title</CardTitle>
  </CardHeader>
  <CardBody>
    Content here
  </CardBody>
</Card>
\```

## Badge
Status indicator with verification colors.

### Usage
\```tsx
import Badge from './components/design-system/Badge';

<Badge variant="confirmed" dot>Confirmed</Badge>
\```

### Variants
- `success`, `warning`, `danger`, `info`, `neutral`
- `confirmed`, `probable`, `alleged`, `contested`, `debunked`
```

#### 3.3 Contributing Guide

**File**: `CONTRIBUTING.md`

```markdown
# Contributing to Triangulate Frontend

## Development Setup

\```bash
# Install dependencies
cd frontend
npm install

# Start dev server
npm run dev

# Run type checking
npm run build

# Run linter
npm run lint
\```

## Coding Standards

### TypeScript
- Use type imports: `import type { Component }`
- Avoid `any` - use proper types or `unknown`
- Use `interface` for object shapes, `type` for unions/primitives

### React
- Functional components with hooks
- Props interfaces for components
- Memoize expensive operations with `useMemo`
- Callback functions with `useCallback`

### Styling
- Use brutalist design tokens from `index.css`
- Follow existing color system
- No rounded corners (border-radius: 2px max)
- High contrast (WCAG AA compliant)

### Git Commits
- Conventional commits format
- Reference issues in commits
- Write clear commit messages

## Pull Request Process

1. Create feature branch from `main`
2. Implement changes with tests
3. Run `npm run build` to verify
4. Create PR with description
5. Request review
6. Address feedback
7. Merge when approved

## Testing

### Manual Testing Checklist
- [ ] All pages load without errors
- [ ] Keyboard navigation works
- [ ] Animations are smooth
- [ ] No console errors
- [ ] Responsive on mobile

### Browser Testing
- Chrome (primary)
- Edge (primary)
- Safari (basic)
- Firefox (basic)
```

#### 3.4 Deployment Guide

**File**: `DEPLOYMENT.md`

```markdown
# Deployment Guide

## Build for Production

\```bash
cd frontend
npm run build
\```

Output will be in `dist/` directory.

## Environment Variables

Required environment variables:
- `VITE_API_BASE_URL` - Backend API URL

## Deployment Options

### Option 1: Static Hosting (Vercel, Netlify)

1. Build the project
2. Deploy `dist/` directory
3. Configure API base URL in environment

### Option 2: Docker

\```dockerfile
FROM node:20-alpine as builder
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
\```

### Option 3: Traditional Server

Serve `dist/` directory with nginx/Apache.

## Post-Deployment Checklist

- [ ] Verify API connectivity
- [ ] Test authentication flow
- [ ] Check all page routes
- [ ] Monitor console for errors
- [ ] Verify bundle size
- [ ] Test on mobile devices

## Rollback Procedure

If deployment fails:
1. Revert to previous commit
2. Redeploy
3. Verify functionality
```

## Implementation Tasks

### Task 1: Animation System (Week 1, Day 1-2)
- [ ] Create `src/lib/animations.ts` with presets
- [ ] Create `src/components/PageTransition.tsx`
- [ ] Create `src/components/StaggeredList.tsx`
- [ ] Create `src/components/LoadingSkeleton.tsx`
- [ ] Update `src/App.tsx` with page transitions
- [ ] Test all page transitions

### Task 2: Design System Animations (Week 1, Day 3-4)
- [ ] Update `Button.tsx` with hover/active states
- [ ] Update `Card.tsx` with hover lift effect
- [ ] Update `Badge.tsx` with scale animation
- [ ] Add focus indicators to all components
- [ ] Test all interactive components

### Task 3: Apply Animations to Pages (Week 1, Day 5)
- [ ] Add staggered lists to `Dashboard.tsx`
- [ ] Add staggered lists to `CaseExplorer.tsx`
- [ ] Add page transitions to tab navigation
- [ ] Test animation performance
- [ ] Adjust timings based on testing

### Task 4: Code Splitting (Week 2, Day 1-2)
- [ ] Update `src/App.tsx` with React.lazy()
- [ ] Create loading fallback components
- [ ] Update `vite.config.ts` with manual chunks
- [ ] Add error boundaries for lazy routes
- [ ] Test lazy loading behavior

### Task 5: Refresh Controls (Week 3, Day 1-2)
- [ ] Create `src/components/RefreshButton.tsx`
- [ ] Create `src/lib/refresh-context.tsx`
- [ ] Add refresh buttons to all data pages
- [ ] Implement "last updated" timestamps
- [ ] Test refresh functionality

### Task 6: Accessibility (Week 3, Day 3-4)
- [ ] Create `src/lib/keyboard-shortcuts.ts`
- [ ] Create `src/lib/focus-manager.ts`
- [ ] Add ARIA labels to all interactive elements
- [ ] Implement keyboard navigation
- [ ] Add visible focus indicators
- [ ] Test with screen reader

### Task 7: Documentation (Week 4, Day 1-3)
- [ ] Write `ARCHITECTURE.md`
- [ ] Write `COMPONENTS.md`
- [ ] Write `CONTRIBUTING.md`
- [ ] Write `DEPLOYMENT.md`
- [ ] Update main README

### Task 8: Testing & Polish (Week 4, Day 4-5)
- [ ] Cross-browser testing (Chrome, Edge, Safari, Firefox)
- [ ] Mobile responsive testing
- [ ] Performance testing (Lighthouse)
- [ ] Accessibility audit (WCAG AA)
- [ ] Fix any issues found
- [ ] Final code review

## Success Criteria

### Performance
- [ ] Initial bundle < 250KB
- [ ] First contentful paint < 2s
- [ ] Time to interactive < 3s
- [ ] Lighthouse score > 90

### User Experience
- [ ] All page transitions smooth (60fps)
- [ ] No janky animations
- [ ] Refresh controls responsive
- [ ] Keyboard navigation works everywhere

### Accessibility
- [ ] All interactive elements keyboard accessible
- [ ] ARIA labels on all icons/buttons
- [ ] Focus indicators visible
- [ ] Screen reader compatible
- [ ] WCAG AA compliant

### Code Quality
- [ ] No TypeScript errors
- [ ] No console warnings
- [ ] All components documented
- [ ] Clean git history

## Handoff Notes

For the next agent continuing this work:

1. **Current State**: Phases 1-4 complete, Phase 5 ready to start
2. **Bundle Size**: 609KB (need to reduce to ~500KB)
3. **Priority**: Start with animations + performance (Week 1-2 tasks)
4. **Key Files**:
   - `src/App.tsx` - Main routing, needs code splitting
   - `src/lib/animations.ts` - Create from scratch
   - `src/components/design-system/` - Enhance with animations
5. **Testing**: Run `npm run build` after each major change
6. **Git**: Commit frequently with descriptive messages

## Rollback Plan

If any task causes issues:
1. Revert the specific commit
2. Verify functionality restored
3. Document the issue
4. Continue with next task

## Next Steps After Phase 5

- User acceptance testing
- Gather feedback on animations
- Performance monitoring in production
- Plan Phase 6 (if needed)

---

**Last Updated**: 2025-03-19
**Status**: Ready for Implementation
**Estimated Effort**: 4 weeks
