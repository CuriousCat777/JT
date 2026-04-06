import { Check } from 'lucide-react';
import { cn } from '@/lib/utils';
import { ONBOARDING_STEPS, usePracticeStore } from '@/stores/practice-store';

interface StepIndicatorProps {
  className?: string;
  onStepClick?: (index: number) => void;
}

function StepIndicator({ className, onStepClick }: StepIndicatorProps) {
  const currentStep = usePracticeStore((s) => s.currentStep);
  const stepsCompleted = usePracticeStore((s) => s.stepsCompleted);

  return (
    <nav className={cn('flex flex-col', className)} aria-label="Onboarding progress">
      <ol className="relative space-y-1">
        {ONBOARDING_STEPS.map((step, index) => {
          const isCompleted = stepsCompleted[step.id];
          const isCurrent = index === currentStep;
          const isUpcoming = index > currentStep && !isCompleted;

          return (
            <li key={step.id} className="relative">
              {/* Connector line */}
              {index < ONBOARDING_STEPS.length - 1 && (
                <div
                  className={cn(
                    'absolute left-[17px] top-[40px] w-0.5 h-[calc(100%-8px)]',
                    isCompleted ? 'bg-primary-600' : 'bg-neutral-200',
                  )}
                  aria-hidden="true"
                />
              )}

              <button
                type="button"
                onClick={() => onStepClick?.(index)}
                className={cn(
                  'flex items-start gap-3 w-full rounded-lg p-3 text-left transition-colors',
                  isCurrent && 'bg-primary-50',
                  !isCurrent && 'hover:bg-neutral-50',
                )}
                aria-current={isCurrent ? 'step' : undefined}
              >
                {/* Step circle */}
                <div
                  className={cn(
                    'flex-shrink-0 flex items-center justify-center w-[34px] h-[34px] rounded-full border-2 transition-colors',
                    isCompleted && 'bg-primary-600 border-primary-600 text-white',
                    isCurrent && !isCompleted && 'border-primary-600 bg-white text-primary-600',
                    isUpcoming && 'border-neutral-300 bg-white text-neutral-400',
                  )}
                >
                  {isCompleted ? (
                    <Check className="w-4 h-4" strokeWidth={3} />
                  ) : (
                    <span className="text-sm font-semibold">{index + 1}</span>
                  )}
                </div>

                {/* Step text */}
                <div className="min-w-0 pt-0.5">
                  <p
                    className={cn(
                      'text-sm font-semibold',
                      isCurrent && 'text-primary-700',
                      isCompleted && 'text-neutral-900',
                      isUpcoming && 'text-neutral-400',
                    )}
                  >
                    {step.label}
                  </p>
                  <p
                    className={cn(
                      'text-xs mt-0.5',
                      isCurrent ? 'text-primary-600' : 'text-neutral-400',
                    )}
                  >
                    {step.description}
                  </p>
                </div>
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

export { StepIndicator };
