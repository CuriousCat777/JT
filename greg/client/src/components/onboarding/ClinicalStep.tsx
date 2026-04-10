import { Monitor, Pill, FlaskConical, Link2, CheckCircle2, Circle } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Select } from '@/components/ui/Select';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { usePracticeStore } from '@/stores/practice-store';

const EHR_SYSTEMS = [
  { value: 'athenahealth', label: 'athenahealth' },
  { value: 'drchrono', label: 'DrChrono' },
  { value: 'practice-fusion', label: 'Practice Fusion' },
  { value: 'elation', label: 'Elation Health' },
  { value: 'kareo', label: 'Kareo / Tebra' },
  { value: 'eclinicalworks', label: 'eClinicalWorks' },
  { value: 'epic-community', label: 'Epic Community Connect' },
  { value: 'openemr', label: 'OpenEMR (Open Source)' },
  { value: 'other', label: 'Other' },
  { value: 'undecided', label: 'Not decided yet' },
];

interface ClinicalFeature {
  id: string;
  label: string;
  description: string;
  icon: React.ReactNode;
  storeKey: 'ePrescribing' | 'labConnectivity' | 'fhirEnabled';
  details: string[];
}

interface ClinicalStepProps {
  onComplete: () => void;
  onBack: () => void;
}

export default function ClinicalStep({ onComplete, onBack }: ClinicalStepProps) {
  const store = usePracticeStore();

  const features: ClinicalFeature[] = [
    {
      id: 'eprescribing',
      label: 'e-Prescribing (EPCS)',
      description: 'Electronic prescribing including controlled substances',
      icon: <Pill className="w-5 h-5 text-violet-600" />,
      storeKey: 'ePrescribing',
      details: [
        'Surescripts connectivity for medication routing',
        'EPCS certification for Schedule II-V substances',
        'Prescription drug monitoring program (PDMP) integration',
        'Medication history and formulary checking',
      ],
    },
    {
      id: 'lab',
      label: 'Lab Connectivity',
      description: 'Electronic lab orders and results',
      icon: <FlaskConical className="w-5 h-5 text-amber-600" />,
      storeKey: 'labConnectivity',
      details: [
        'Quest Diagnostics and Labcorp interfaces',
        'Local/regional lab connectivity',
        'Electronic order entry and result routing',
        'Abnormal result alerts and tracking',
      ],
    },
    {
      id: 'fhir',
      label: 'FHIR Bridge',
      description: 'HL7 FHIR R4 interoperability for health data exchange',
      icon: <Link2 className="w-5 h-5 text-primary-600" />,
      storeKey: 'fhirEnabled',
      details: [
        'Patient record exchange via USCDI v3',
        'Health Information Exchange (HIE) participation',
        'Referral and transition-of-care documents',
        '21st Century Cures Act compliance',
      ],
    },
  ];

  const handleContinue = () => {
    store.completeStep('clinical');
    onComplete();
  };

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-2xl font-bold text-neutral-900">Clinical Setup</h2>
        <p className="text-neutral-500 mt-1">
          VITALS configures your EHR, e-prescribing, lab connectivity, and FHIR interoperability.
        </p>
      </div>

      {/* EHR Selection */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Monitor className="w-5 h-5 text-primary-600" />
            Electronic Health Records (EHR)
          </CardTitle>
          <CardDescription>
            Choose a certified EHR system for your practice
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Select
            label="EHR System"
            placeholder="Select your EHR"
            options={EHR_SYSTEMS}
            value={store.ehrSystem}
            onChange={(e) => store.setField('ehrSystem', e.target.value)}
            helperText="All listed systems are ONC-certified for Meaningful Use"
          />

          {store.ehrSystem && store.ehrSystem !== 'undecided' && (
            <div className="p-4 rounded-lg bg-accent-50 border border-accent-200">
              <p className="text-sm font-medium text-accent-800">
                VITALS will configure {store.ehrSystem} with:
              </p>
              <ul className="text-sm text-accent-700 mt-2 space-y-1">
                <li>- Practice demographics and provider profiles</li>
                <li>- Custom templates for {store.specialty || 'your specialty'}</li>
                <li>- Patient portal activation</li>
                <li>- Clinical decision support rules</li>
                <li>- Reporting dashboards (MIPS/quality measures)</li>
              </ul>
            </div>
          )}

          {store.ehrSystem === 'undecided' && (
            <div className="p-4 rounded-lg bg-blue-50 border border-blue-200">
              <p className="text-sm font-medium text-blue-800">
                VITALS Recommendation for {store.practiceType || 'solo'} practices:
              </p>
              <div className="mt-2 space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-blue-700">athenahealth</span>
                  <Badge variant="success">Best Overall</Badge>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-blue-700">Elation Health</span>
                  <Badge variant="info">Best UX</Badge>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-blue-700">OpenEMR</span>
                  <Badge variant="info">Best Budget</Badge>
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Clinical Features */}
      <div className="space-y-4">
        {features.map((feature) => {
          const enabled = store[feature.storeKey];
          return (
            <Card key={feature.id} className={enabled ? 'border-primary-200' : ''}>
              <CardContent className="py-4">
                <div className="flex items-start gap-4">
                  <button
                    type="button"
                    onClick={() => store.setField(feature.storeKey, !enabled)}
                    className="flex-shrink-0 mt-0.5"
                  >
                    {enabled ? (
                      <CheckCircle2 className="w-6 h-6 text-primary-600" />
                    ) : (
                      <Circle className="w-6 h-6 text-neutral-300" />
                    )}
                  </button>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      {feature.icon}
                      <h4 className="font-semibold text-neutral-900">{feature.label}</h4>
                      {enabled && <Badge variant="success">Enabled</Badge>}
                    </div>
                    <p className="text-sm text-neutral-500 mt-1">{feature.description}</p>
                    {enabled && (
                      <ul className="mt-3 space-y-1">
                        {feature.details.map((detail) => (
                          <li key={detail} className="text-sm text-neutral-600 flex items-start gap-2">
                            <span className="text-primary-400 mt-1 text-xs">--</span>
                            {detail}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <div className="flex justify-between pt-4">
        <Button type="button" variant="ghost" onClick={onBack}>
          Back
        </Button>
        <Button type="button" onClick={handleContinue}>
          Continue to Financial Setup
        </Button>
      </div>
    </div>
  );
}
