import { type FC } from 'react'
import { detailedEval, type DetailedEvaluation } from '../data/mockData'
import ReportOverview, { type ReportStep } from './ReportOverview'
import ExpertAnalysis from './ExpertAnalysis'
import CouncilReview from './CouncilReview'
import FinalReport from './FinalReport'
import type { CouncilReportResponse } from '../api/client'

interface Props {
  evaluationId: string
  step: ReportStep
  onStepChange: (step: ReportStep) => void
  evaluation?: DetailedEvaluation | null
  councilReport?: CouncilReportResponse | null
  onViewFull?: () => void
}

const Report: FC<Props> = ({ evaluationId, step, onStepChange, evaluation, councilReport, onViewFull }) => {
  const evalData = evaluation ?? (evaluationId === detailedEval.agent_id ? detailedEval : null)
  const expert1Report = councilReport?.expert_reports?.security ?? null
  if (!evalData) {
    return (
      <div className="p-8 animate-fade-in">
        <p className="text-apple-gray-500">Evaluation not loaded. Open from Dashboard history or submit a new evaluation.</p>
      </div>
    )
  }

  if (step === 'overview') {
    return (
      <ReportOverview
        eval={evalData}
        currentStep={step}
        onStep={onStepChange}
        expert1Report={expert1Report ?? undefined}
        onViewFull={onViewFull}
      />
    )
  }
  if (step === 'experts') return <ExpertAnalysis evaluation={evalData} />
  if (step === 'council') return <CouncilReview evaluation={evalData} />
  if (step === 'final') return <FinalReport evaluation={evalData} />
  return null
}

export default Report
export type { ReportStep }
