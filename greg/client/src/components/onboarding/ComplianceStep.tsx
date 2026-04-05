import { useState } from 'react';
import { ShieldCheck, CheckSquare, Square, AlertTriangle, FileCheck } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { usePracticeStore } from '@/stores/practice-store';

interface ChecklistItem {
  id: string;
  label: string;
  description: string;
  required: boolean;
  completed: boolean;
}

interface ComplianceStepProps {
  onComplete: () => void;
  onBack: () => void;
}

export default function ComplianceStep({ onComplete, onBack }: ComplianceStepProps) {
  const store = usePracticeStore();

  const [hipaaChecklist, setHipaaChecklist] = useState<ChecklistItem[]>([
    {
      id: 'privacy-officer',
      label: 'Designate Privacy Officer',
      description: 'Required HIPAA role -- can be yourself in a solo practice',
      required: true,
      completed: false,
    },
    {
      id: 'security-officer',
      label: 'Designate Security Officer',
      description: 'Oversees electronic PHI protections',
      required: true,
      completed: false,
    },
    {
      id: 'risk-assessment',
      label: 'Conduct Risk Assessment',
      description: 'Annual assessment of threats to PHI',
      required: true,
      completed: false,
    },
    {
      id: 'policies',
      label: 'Develop Privacy & Security Policies',
      description: 'Written policies covering PHI handling, breach response, etc.',
      required: true,
      completed: false,
    },
    {
      id: 'baa',
      label: 'Prepare BAA Templates',
      description: 'Business Associate Agreements for vendors handling PHI',
      required: true,
      completed: false,
    },
    {
      id: 'training',
      label: 'Staff Training Program',
      description: 'HIPAA training for all workforce members',
      required: true,
      completed: false,
    },
    {
      id: 'notice-of-privacy',
      label: 'Notice of Privacy Practices',
      description: 'Patient-facing document describing PHI use',
      required: true,
      completed: false,
    },
    {
      id: 'breach-plan',
      label: 'Breach Notification Plan',
      description: 'Procedures for responding to a PHI breach',
      required: true,
      completed: false,
    },
  ]);

  const toggleChecklistItem = (id: string) => {
    setHipaaChecklist((prev) =>
      prev.map((item) => (item.id === id ? { ...item, completed: !item.completed } : item)),
    );
  };

  const completedCount = hipaaChecklist.filter((i) => i.completed).length;
  const totalRequired = hipaaChecklist.filter((i) => i.required).length;

  const handleContinue = () => {
    store.completeStep('compliance');
    onComplete();
  };

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-2xl font-bold text-neutral-900">Regulatory Compliance</h2>
        <p className="text-neutral-500 mt-1">
          COMPLY ensures your practice meets CMS, HIPAA, OIG, and CLIA requirements.
        </p>
      </div>

      {/* CMS Enrollment */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileCheck className="w-5 h-5 text-primary-600" />
            CMS / Medicare Enrollment
          </CardTitle>
          <CardDescription>
            Enroll in PECOS (Provider Enrollment, Chain, and Ownership System)
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between p-3 rounded-lg bg-neutral-50 border border-neutral-200">
            <div>
              <p className="text-sm font-medium text-neutral-900">Medicare Enrollment (CMS-855I)</p>
              <p className="text-xs text-neutral-500">Individual provider enrollment -- required for Medicare billing</p>
            </div>
            <div className="flex items-center gap-3">
              <Badge variant={store.cmsEnrolled ? 'success' : 'pending'}>
                {store.cmsEnrolled ? 'Enrolled' : 'Not Started'}
              </Badge>
              <Button
                size="sm"
                variant={store.cmsEnrolled ? 'ghost' : 'primary'}
                onClick={() => store.setField('cmsEnrolled', !store.cmsEnrolled)}
              >
                {store.cmsEnrolled ? 'Undo' : 'Mark Complete'}
              </Button>
            </div>
          </div>
          <div className="text-sm text-neutral-500 space-y-1">
            <p>Estimated processing time: 60-90 days</p>
            <p>Apply at: pecos.cms.hhs.gov</p>
          </div>
        </CardContent>
      </Card>

      {/* OIG Check */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <ShieldCheck className="w-5 h-5 text-primary-600" />
                OIG Exclusion Check
              </CardTitle>
              <CardDescription>
                Verify you are not on the OIG exclusion list
              </CardDescription>
            </div>
            <Badge variant={store.oigClear ? 'success' : 'pending'}>
              {store.oigClear ? 'Clear' : 'Not Checked'}
            </Badge>
          </div>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            <p className="text-sm text-neutral-600">
              The Office of Inspector General maintains a list of excluded individuals/entities.
              Being on this list bars participation in federal healthcare programs.
            </p>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => store.setField('oigClear', true)}
              className="flex-shrink-0 ml-4"
            >
              Run OIG Check
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* HIPAA Checklist */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <ShieldCheck className="w-5 h-5 text-primary-600" />
                HIPAA Compliance Checklist
              </CardTitle>
              <CardDescription>
                {completedCount} of {totalRequired} required items completed
              </CardDescription>
            </div>
            <Badge variant={completedCount === totalRequired ? 'success' : 'warning'}>
              {Math.round((completedCount / totalRequired) * 100)}%
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="divide-y divide-neutral-100">
          {hipaaChecklist.map((item) => (
            <button
              key={item.id}
              type="button"
              className="flex items-start gap-3 w-full py-3 text-left hover:bg-neutral-50 rounded -mx-2 px-2 transition-colors"
              onClick={() => toggleChecklistItem(item.id)}
            >
              {item.completed ? (
                <CheckSquare className="w-5 h-5 text-primary-600 flex-shrink-0 mt-0.5" />
              ) : (
                <Square className="w-5 h-5 text-neutral-400 flex-shrink-0 mt-0.5" />
              )}
              <div>
                <p
                  className={`text-sm font-medium ${
                    item.completed ? 'text-neutral-400 line-through' : 'text-neutral-900'
                  }`}
                >
                  {item.label}
                  {item.required && <span className="text-red-400 ml-1">*</span>}
                </p>
                <p className="text-xs text-neutral-500 mt-0.5">{item.description}</p>
              </div>
            </button>
          ))}
        </CardContent>
      </Card>

      {/* CLIA */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-amber-500" />
            CLIA Waiver (If Applicable)
          </CardTitle>
          <CardDescription>
            Required if you will perform any lab tests in your office
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 text-sm text-neutral-700 cursor-pointer">
              <input
                type="checkbox"
                checked={store.cliaRequired}
                onChange={(e) => store.setField('cliaRequired', e.target.checked)}
                className="rounded border-neutral-300 text-primary-600 focus:ring-primary-500"
              />
              I plan to perform CLIA-waived tests in my office
            </label>
          </div>
          {store.cliaRequired && (
            <Input
              label="CLIA Number"
              placeholder="CLIA certificate number"
              value={store.cliaNumber}
              onChange={(e) => store.setField('cliaNumber', e.target.value)}
              helperText="Apply at cms.gov/clia -- biennial fee ~$180 for waived tests"
            />
          )}
        </CardContent>
      </Card>

      <div className="flex justify-between pt-4">
        <Button type="button" variant="ghost" onClick={onBack}>
          Back
        </Button>
        <Button type="button" onClick={handleContinue}>
          Continue to Clinical Setup
        </Button>
      </div>
    </div>
  );
}
