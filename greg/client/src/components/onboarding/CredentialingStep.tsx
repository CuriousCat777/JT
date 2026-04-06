import { useState } from 'react';
import { Shield, Search, CheckCircle2, AlertCircle, Clock, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { usePracticeStore } from '@/stores/practice-store';

type CredentialStatus = 'unchecked' | 'checking' | 'valid' | 'invalid' | 'expired';

interface CredentialCheck {
  label: string;
  description: string;
  status: CredentialStatus;
  detail?: string;
}

interface CredentialingStepProps {
  onComplete: () => void;
  onBack: () => void;
}

export default function CredentialingStep({ onComplete, onBack }: CredentialingStepProps) {
  const store = usePracticeStore();
  const [isChecking, setIsChecking] = useState(false);

  const [credentials, setCredentials] = useState<CredentialCheck[]>([
    {
      label: 'NPI Number',
      description: 'National Provider Identifier verification via NPPES',
      status: store.npiNumber ? 'valid' : 'unchecked',
    },
    {
      label: 'State Medical License',
      description: `Active license in ${store.targetState || 'your target state'}`,
      status: store.stateLicense ? 'valid' : 'unchecked',
    },
    {
      label: 'DEA Registration',
      description: 'Drug Enforcement Administration registration',
      status: store.deaNumber ? 'valid' : 'unchecked',
    },
    {
      label: 'Board Certification',
      description: 'ABMS board certification status',
      status: store.boardCertification ? 'valid' : 'unchecked',
    },
    {
      label: 'Malpractice Insurance',
      description: 'Active professional liability coverage',
      status: store.malpracticeInsurance ? 'valid' : 'unchecked',
    },
  ]);

  const runCredentialCheck = async () => {
    setIsChecking(true);

    // Simulate CREDENCE agent checking credentials one by one
    for (let i = 0; i < credentials.length; i++) {
      setCredentials((prev) =>
        prev.map((c, idx) => (idx === i ? { ...c, status: 'checking' as CredentialStatus } : c)),
      );

      await new Promise((resolve) => setTimeout(resolve, 800 + Math.random() * 600));

      const isValid = Math.random() > 0.2;
      setCredentials((prev) =>
        prev.map((c, idx) =>
          idx === i
            ? {
                ...c,
                status: (isValid ? 'valid' : 'invalid') as CredentialStatus,
                detail: isValid
                  ? 'Verified successfully'
                  : 'Could not verify -- manual review needed',
              }
            : c,
        ),
      );
    }

    setIsChecking(false);
  };

  const statusIcon = (status: CredentialStatus) => {
    switch (status) {
      case 'valid':
        return <CheckCircle2 className="w-5 h-5 text-emerald-600" />;
      case 'invalid':
      case 'expired':
        return <AlertCircle className="w-5 h-5 text-red-500" />;
      case 'checking':
        return (
          <div className="w-5 h-5 border-2 border-primary-600 border-t-transparent rounded-full animate-spin" />
        );
      default:
        return <Clock className="w-5 h-5 text-neutral-400" />;
    }
  };

  const statusBadge = (status: CredentialStatus) => {
    switch (status) {
      case 'valid':
        return <Badge variant="success">Verified</Badge>;
      case 'invalid':
        return <Badge variant="error">Needs Review</Badge>;
      case 'expired':
        return <Badge variant="warning">Expired</Badge>;
      case 'checking':
        return <Badge variant="info">Checking...</Badge>;
      default:
        return <Badge variant="pending">Not Checked</Badge>;
    }
  };

  const allVerified = credentials.every((c) => c.status === 'valid');

  const handleContinue = () => {
    store.completeStep('credentialing');
    onComplete();
  };

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-2xl font-bold text-neutral-900">Credentialing</h2>
        <p className="text-neutral-500 mt-1">
          CREDENCE verifies your licenses, certifications, and registrations against national databases.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Input
          label="NPI Number"
          placeholder="10-digit NPI"
          value={store.npiNumber}
          onChange={(e) => store.setField('npiNumber', e.target.value)}
          helperText="Your unique National Provider Identifier"
        />
        <Input
          label="State License Number"
          placeholder="License number"
          value={store.stateLicense}
          onChange={(e) => store.setField('stateLicense', e.target.value)}
          helperText={`Medical license for ${store.targetState || 'your state'}`}
        />
        <Input
          label="DEA Number"
          placeholder="DEA registration number"
          value={store.deaNumber}
          onChange={(e) => store.setField('deaNumber', e.target.value)}
          helperText="Required for prescribing controlled substances"
        />
        <Input
          label="Board Certification"
          placeholder="e.g., ABFM Family Medicine"
          value={store.boardCertification}
          onChange={(e) => store.setField('boardCertification', e.target.value)}
          helperText="ABMS board certification"
        />
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Shield className="w-5 h-5 text-primary-600" />
                Credential Verification
              </CardTitle>
              <CardDescription>
                CREDENCE checks NPI, state license, DEA, and board status
              </CardDescription>
            </div>
            <Button
              onClick={runCredentialCheck}
              loading={isChecking}
              disabled={isChecking}
              variant="secondary"
            >
              <Search className="w-4 h-4" />
              Check My Credentials
            </Button>
          </div>
        </CardHeader>
        <CardContent className="divide-y divide-neutral-100">
          {credentials.map((cred) => (
            <div key={cred.label} className="flex items-center gap-4 py-3 first:pt-0 last:pb-0">
              {statusIcon(cred.status)}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-neutral-900">{cred.label}</p>
                <p className="text-xs text-neutral-500">{cred.description}</p>
                {cred.detail && (
                  <p className="text-xs text-neutral-400 mt-0.5">{cred.detail}</p>
                )}
              </div>
              {statusBadge(cred.status)}
            </div>
          ))}
        </CardContent>
      </Card>

      <Card className="border-blue-200 bg-blue-50/50">
        <CardContent className="flex items-start gap-3 py-3">
          <ExternalLink className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-blue-800">Need to apply for credentials?</p>
            <ul className="text-sm text-blue-600 mt-1 space-y-1">
              <li>NPI: Apply free at nppes.cms.hhs.gov (takes ~10 days)</li>
              <li>DEA: Apply at deadiversion.usdoj.gov ($888 for 3 years)</li>
              <li>State License: Contact your state medical board</li>
            </ul>
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-between pt-4">
        <Button type="button" variant="ghost" onClick={onBack}>
          Back
        </Button>
        <Button type="button" onClick={handleContinue} disabled={!allVerified && isChecking}>
          {allVerified ? 'Continue to Business Formation' : 'Skip for Now'}
        </Button>
      </div>
    </div>
  );
}
