import { useEffect, useState } from 'react'
import Sidebar from './components/Sidebar'
import Dashboard from './pages/Dashboard'
import NewEvaluation from './pages/NewEvaluation'
import Report from './pages/Report'
import type { ReportStep } from './pages/Report'
import ReportFullPage from './pages/ReportFullPage'
import {
  getEvaluationByIncident,
  listEvaluations,
  type CouncilReportResponse,
  type EvaluationListItem,
} from './api/client'
import { councilReportToDetailedEvaluation } from './utils/mapCouncilReport'
import type { DetailedEvaluation } from './data/mockData'

type Page = 'dashboard' | 'evaluate' | 'report' | 'fullreport'

function App() {
  const [page, setPage] = useState<Page>('dashboard')
  const [reportId, setReportId] = useState<string | null>(null)
  const [reportStep, setReportStep] = useState<ReportStep>('overview')
  const [evaluations, setEvaluations] = useState<EvaluationListItem[]>([])
  const [currentReport, setCurrentReport] = useState<CouncilReportResponse | null>(null)
  const [currentEvaluation, setCurrentEvaluation] = useState<DetailedEvaluation | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  const loadHistory = async () => {
    try {
      setLoadError(null)
      const rows = await listEvaluations(50, 0)
      setEvaluations(rows)
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : String(e))
      setEvaluations([])
    }
  }

  useEffect(() => {
    void loadHistory()
  }, [])

  const openReport = (id: string, step: ReportStep = 'overview') => {
    setReportId(id)
    setReportStep(step)
    setPage('report')
  }

  const openFullReport = (id: string) => {
    setReportId(id)
    setPage('fullreport')
  }

  const handleSelectEval = async (incidentId: string) => {
    try {
      const report = await getEvaluationByIncident(incidentId)
      setCurrentReport(report)
      setCurrentEvaluation(councilReportToDetailedEvaluation(report))
      openReport(incidentId)
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : String(e))
    }
  }

  const handleEvalSubmit = (report: CouncilReportResponse) => {
    setCurrentReport(report)
    setCurrentEvaluation(councilReportToDetailedEvaluation(report))
    void loadHistory()
    openReport(report.incident_id)
  }

  // Full-page standalone view — no sidebar
  if (page === 'fullreport' && reportId) {
    return (
      <ReportFullPage
        incidentId={reportId}
        onBack={() => setPage('report')}
      />
    )
  }

  return (
    <div className="flex min-h-screen bg-apple-gray-50">
      <Sidebar
        current={page}
        reportStep={reportStep}
        onPageChange={setPage}
        onReportStepChange={setReportStep}
        showReportSubNav={!!reportId}
      />
      <main className="flex-1 overflow-auto">
        {page === 'dashboard' && (
          <Dashboard
            onSelect={handleSelectEval}
            onNewEvaluation={() => setPage('evaluate')}
            evaluations={evaluations}
          />
        )}
        {page === 'evaluate' && <NewEvaluation onSubmit={handleEvalSubmit} />}
        {loadError && (
          <div className="mx-8 mt-4 p-3 rounded-apple bg-apple-red-bg border border-apple-red/30 text-sm text-apple-red">
            API error: {loadError}
          </div>
        )}
        {page === 'report' && reportId && (
          <Report
            evaluationId={reportId}
            step={reportStep}
            onStepChange={setReportStep}
            evaluation={currentEvaluation}
            councilReport={currentReport}
            onViewFull={() => openFullReport(reportId)}
          />
        )}
      </main>
    </div>
  )
}

export default App
