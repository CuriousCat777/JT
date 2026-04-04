import { Building2, FileText, Info } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { usePracticeStore } from '@/stores/practice-store';

const ENTITY_TYPES = [
  { value: 'pllc', label: 'PLLC (Professional Limited Liability Company)' },
  { value: 'pc', label: 'PC (Professional Corporation)' },
  { value: 'pa', label: 'PA (Professional Association)' },
  { value: 'sole-prop', label: 'Sole Proprietorship' },
  { value: 'partnership', label: 'Partnership' },
  { value: 's-corp', label: 'S-Corporation' },
];

interface EntityRecommendation {
  type: string;
  label: string;
  pros: string[];
  cons: string[];
  recommended: boolean;
}

const RECOMMENDATIONS: EntityRecommendation[] = [
  {
    type: 'pllc',
    label: 'PLLC',
    pros: [
      'Personal asset protection from business liabilities',
      'Pass-through taxation (no double taxation)',
      'Flexible management structure',
      'Lower compliance burden than corporations',
    ],
    cons: [
      'Does not protect against personal malpractice',
      'Self-employment taxes on all profits',
      'May have higher state fees in some states',
    ],
    recommended: true,
  },
  {
    type: 'pc',
    label: 'Professional Corporation',
    pros: [
      'Well-established legal structure for medical practices',
      'Can elect S-Corp tax status',
      'May offer better retirement plan options',
    ],
    cons: [
      'More administrative overhead',
      'Required board meetings and minutes',
      'Double taxation if C-Corp status',
    ],
    recommended: false,
  },
  {
    type: 's-corp',
    label: 'S-Corporation',
    pros: [
      'Potential self-employment tax savings',
      'Salary/distribution split optimization',
      'Pass-through taxation',
    ],
    cons: [
      'Strict ownership requirements',
      'Reasonable salary requirement',
      'More complex tax filings',
    ],
    recommended: false,
  },
];

interface FormationStepProps {
  onComplete: () => void;
  onBack: () => void;
}

export default function FormationStep({ onComplete, onBack }: FormationStepProps) {
  const store = usePracticeStore();

  const handleContinue = () => {
    store.completeStep('formation');
    onComplete();
  };

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-2xl font-bold text-neutral-900">Business Formation</h2>
        <p className="text-neutral-500 mt-1">
          FORMA helps you establish the right legal entity and register your practice.
        </p>
      </div>

      {/* Recommended entity type */}
      <Card className="border-accent-200 bg-accent-50/30">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Building2 className="w-5 h-5 text-accent-600" />
            FORMA Recommendation
          </CardTitle>
          <CardDescription>
            Based on a {store.practiceType || 'solo'} practice in{' '}
            {store.targetState || 'your state'}, we recommend:
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-6">
            {RECOMMENDATIONS.map((rec) => (
              <div
                key={rec.type}
                className={`rounded-lg border p-4 ${
                  rec.recommended
                    ? 'border-accent-300 bg-white ring-2 ring-accent-200'
                    : 'border-neutral-200 bg-white'
                }`}
              >
                <div className="flex items-center gap-2 mb-2">
                  <h4 className="font-semibold text-neutral-900">{rec.label}</h4>
                  {rec.recommended && <Badge variant="success">Recommended</Badge>}
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <p className="text-xs font-medium text-emerald-700 mb-1">Advantages</p>
                    <ul className="text-sm text-neutral-600 space-y-1">
                      {rec.pros.map((pro) => (
                        <li key={pro} className="flex items-start gap-1.5">
                          <span className="text-emerald-500 mt-1">+</span>
                          {pro}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <p className="text-xs font-medium text-red-600 mb-1">Considerations</p>
                    <ul className="text-sm text-neutral-600 space-y-1">
                      {rec.cons.map((con) => (
                        <li key={con} className="flex items-start gap-1.5">
                          <span className="text-red-400 mt-1">-</span>
                          {con}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Formation form */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileText className="w-5 h-5 text-primary-600" />
            Entity Details
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="md:col-span-2">
              <Input
                label="Practice Name"
                placeholder="e.g., Boundary Waters Family Medicine, PLLC"
                value={store.practiceName}
                onChange={(e) => store.setField('practiceName', e.target.value)}
                helperText="Check name availability with your Secretary of State"
              />
            </div>
            <Select
              label="Entity Type"
              placeholder="Select entity type"
              options={ENTITY_TYPES}
              value={store.entityType}
              onChange={(e) => store.setField('entityType', e.target.value)}
            />
            <Input
              label="EIN (Employer Identification Number)"
              placeholder="XX-XXXXXXX"
              value={store.ein}
              onChange={(e) => store.setField('ein', e.target.value)}
              helperText="Apply free at irs.gov/ein -- instant online"
            />
            <div className="md:col-span-2">
              <Input
                label="Business Address"
                placeholder="Street address for your practice"
                value={store.businessAddress}
                onChange={(e) => store.setField('businessAddress', e.target.value)}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* State-specific requirements */}
      <Card className="border-blue-200 bg-blue-50/50">
        <CardContent className="flex items-start gap-3 py-4">
          <Info className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-blue-800">
              {store.targetState || 'State'} Formation Checklist
            </p>
            <ul className="text-sm text-blue-600 mt-2 space-y-1.5">
              <li>1. File Articles of Organization with Secretary of State</li>
              <li>2. Draft Operating Agreement (required for PLLC)</li>
              <li>3. Apply for EIN with the IRS (free, instant online)</li>
              <li>4. Register for state tax accounts</li>
              <li>5. Obtain a business bank account</li>
              <li>6. Register with the state medical board as a practice entity</li>
            </ul>
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-between pt-4">
        <Button type="button" variant="ghost" onClick={onBack}>
          Back
        </Button>
        <Button type="button" onClick={handleContinue}>
          Continue to Compliance
        </Button>
      </div>
    </div>
  );
}
