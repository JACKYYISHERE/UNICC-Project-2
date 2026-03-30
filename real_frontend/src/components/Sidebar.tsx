import { type FC } from 'react'
import { hapticSelect } from '../utils/haptic'
import type { ReportStep } from '../pages/Report'

type Page = 'dashboard' | 'evaluate' | 'report' | 'fullreport'

const REPORT_STEPS: { id: ReportStep; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'experts', label: 'Expert Analysis' },
  { id: 'council', label: 'Council Review' },
  { id: 'final', label: 'Final Report' },
]

interface Props {
  current: Page
  reportStep?: ReportStep
  onPageChange: (p: Page) => void
  onReportStepChange?: (step: ReportStep) => void
  showReportSubNav?: boolean
}

const Sidebar: FC<Props> = ({
  current,
  reportStep = 'overview',
  onPageChange,
  onReportStepChange,
  showReportSubNav = false,
}) => {
  const handleNav = (page: Page) => {
    hapticSelect()
    onPageChange(page)
  }

  const handleReportStep = (step: ReportStep) => {
    hapticSelect()
    onPageChange('report')
    onReportStepChange?.(step)
  }

  return (
    <aside className="w-60 shrink-0 flex flex-col h-screen sticky top-0 bg-white border-r border-apple-gray-100">
      <div className="px-6 pt-8 pb-6">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-xl bg-apple-blue flex items-center justify-center">
            <span className="text-white text-sm font-bold leading-none">U</span>
          </div>
          <div>
            <div className="text-sm font-bold text-apple-gray-900 leading-tight">UNICC</div>
            <div className="text-[10px] font-medium text-apple-gray-400 leading-tight tracking-wide uppercase">AI Safety Council</div>
          </div>
        </div>
      </div>

      <nav className="flex-1 px-3 space-y-0.5 overflow-auto">
        <div className="section-label px-4 mb-4">Navigation</div>
        <button
          onClick={() => handleNav('dashboard')}
          className={`nav-item w-full text-left ${current === 'dashboard' ? 'active' : ''}`}
        >
          <span className="text-base w-5 text-center">⬡</span>
          <span>Dashboard</span>
        </button>
        <button
          onClick={() => handleNav('evaluate')}
          className={`nav-item w-full text-left ${current === 'evaluate' ? 'active' : ''}`}
        >
          <span className="text-base w-5 text-center">＋</span>
          <span>New Evaluation</span>
        </button>

        {showReportSubNav && (
          <>
            <div className="section-label px-4 mt-6 mb-2">Report</div>
            {REPORT_STEPS.map(({ id, label }) => (
              <button
                key={id}
                onClick={() => handleReportStep(id)}
                className={`nav-item w-full text-left pl-8 ${current === 'report' && reportStep === id ? 'active' : ''}`}
              >
                <span className="text-base w-5 text-center opacity-70">{id === 'overview' ? '▤' : id === 'experts' ? '◈' : id === 'council' ? '◉' : '▦'}</span>
                <span>{label}</span>
              </button>
            ))}
          </>
        )}
      </nav>

      <div className="px-6 pb-6">
        <div className="p-3 rounded-apple bg-apple-gray-50 border border-apple-gray-100">
          <div className="flex items-center gap-2 mb-1">
            <span className="w-1.5 h-1.5 rounded-full bg-apple-green animate-pulse-dot" />
            <span className="text-xs font-semibold text-apple-gray-900">System Online</span>
          </div>
          <p className="text-[11px] text-apple-gray-400 leading-snug">3 Experts · 1 Council</p>
        </div>
      </div>
    </aside>
  )
}

export default Sidebar
