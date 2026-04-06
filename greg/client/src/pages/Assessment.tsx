import { Link } from 'react-router-dom';
import { Stethoscope, ArrowLeft } from 'lucide-react';
import { StepIndicator } from '@/components/ui/StepIndicator';
import { ProgressBar } from '@/components/ui/ProgressBar';
import { usePracticeStore, ONBOARDING_STEPS } from '@/stores/practice-store';

import AssessmentForm from '@/components/onboarding/AssessmentForm';
import CredentialingStep from '@/components/onboarding/CredentialingStep';
import FormationStep from '@/components/onboarding/FormationStep';
import ComplianceStep from '@/components/onboarding/ComplianceStep';
import ClinicalStep from '@/components/onboarding/ClinicalStep';
import FinancialStep from '@/components/onboarding/FinancialStep';
import LaunchStep from '@/components/onboarding/LaunchStep';

export default function Assessment() {
  const { currentStep, nextStep, prevStep, goToStep, stepsCompleted } = usePracticeStore();

  const completedCount = Object.values(stepsCompleted).filter(Boolean).length;
  const overallProgress = (completedCount / ONBOARDING_STEPS.length) * 100;

  const renderStep = () => {
    switch (currentStep) {
      case 0:
        return <AssessmentForm onComplete={nextStep} />;
      case 1:
        return <CredentialingStep onComplete={nextStep} onBack={prevStep} />;
      case 2:
        return <FormationStep onComplete={nextStep} onBack={prevStep} />;
      case 3:
        return <ComplianceStep onComplete={nextStep} onBack={prevStep} />;
      case 4:
        return <ClinicalStep onComplete={nextStep} onBack={prevStep} />;
      case 5:
        return <FinancialStep onComplete={nextStep} onBack={prevStep} />;
      case 6:
        return <LaunchStep onBack={prevStep} />;
      default:
        return <AssessmentForm onComplete={nextStep} />;
    }
  };

  return (
    <div className="min-h-screen bg-neutral-50">
      {/* Top bar */}
      <header className="sticky top-0 z-50 bg-white border-b border-neutral-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-14">
            <Link to="/" className="flex items-center gap-2 text-neutral-600 hover:text-neutral-900 transition-colors">
              <ArrowLeft className="w-4 h-4" />
              <Stethoscope className="w-5 h-5 text-primary-700" />
              <span className="text-sm font-semibold text-neutral-900">GREG.ai</span>
            </Link>
            <div className="flex items-center gap-4">
              <span className="text-xs text-neutral-500 hidden sm:inline">
                Step {currentStep + 1} of {ONBOARDING_STEPS.length}
              </span>
              <ProgressBar
                value={overallProgress}
                size="sm"
                variant="accent"
                className="w-32"
              />
            </div>
          </div>
        </div>
      </header>

      {/* Main content */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="flex gap-8">
          {/* Sidebar: Step indicator (desktop) */}
          <aside className="hidden lg:block w-72 flex-shrink-0">
            <div className="sticky top-24">
              <StepIndicator onStepClick={goToStep} />
            </div>
          </aside>

          {/* Main form area */}
          <main className="flex-1 min-w-0 max-w-3xl">
            <div className="animate-fade-in">{renderStep()}</div>
          </main>
        </div>
      </div>
    </div>
  );
}
