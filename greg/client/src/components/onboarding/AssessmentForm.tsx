import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { MapPin, Lightbulb } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { Card, CardContent } from '@/components/ui/Card';
import { usePracticeStore } from '@/stores/practice-store';

const assessmentSchema = z.object({
  physicianName: z.string().min(2, 'Name is required'),
  targetState: z.string().min(1, 'Select a state'),
  targetCity: z.string().min(1, 'Enter a city'),
  specialty: z.string().min(1, 'Select a specialty'),
  practiceType: z.string().min(1, 'Select practice type'),
  timeline: z.string().min(1, 'Select a timeline'),
  budget: z.string().min(1, 'Select a budget range'),
  experienceLevel: z.string().min(1, 'Select experience level'),
});

type AssessmentFormData = z.infer<typeof assessmentSchema>;

const SPECIALTIES = [
  { value: 'family-medicine', label: 'Family Medicine' },
  { value: 'internal-medicine', label: 'Internal Medicine' },
  { value: 'pediatrics', label: 'Pediatrics' },
  { value: 'ob-gyn', label: 'OB/GYN' },
  { value: 'psychiatry', label: 'Psychiatry' },
  { value: 'dermatology', label: 'Dermatology' },
  { value: 'orthopedics', label: 'Orthopedics' },
  { value: 'cardiology', label: 'Cardiology' },
  { value: 'emergency-medicine', label: 'Emergency Medicine' },
  { value: 'general-surgery', label: 'General Surgery' },
  { value: 'other', label: 'Other' },
];

const PRACTICE_TYPES = [
  { value: 'solo', label: 'Solo Practice' },
  { value: 'small-group', label: 'Small Group (2-5 providers)' },
  { value: 'concierge', label: 'Concierge / DPC' },
  { value: 'telehealth', label: 'Telehealth-Only' },
  { value: 'hybrid', label: 'Hybrid (In-person + Telehealth)' },
  { value: 'urgent-care', label: 'Urgent Care' },
];

const TIMELINES = [
  { value: '3-months', label: '3 months or less' },
  { value: '6-months', label: '3-6 months' },
  { value: '12-months', label: '6-12 months' },
  { value: '12-plus', label: '12+ months' },
];

const BUDGETS = [
  { value: 'under-50k', label: 'Under $50,000' },
  { value: '50k-100k', label: '$50,000 - $100,000' },
  { value: '100k-250k', label: '$100,000 - $250,000' },
  { value: '250k-500k', label: '$250,000 - $500,000' },
  { value: '500k-plus', label: '$500,000+' },
];

const EXPERIENCE_LEVELS = [
  { value: 'resident', label: 'Current Resident / Fellow' },
  { value: 'early-career', label: 'Early Career (0-5 years)' },
  { value: 'mid-career', label: 'Mid Career (5-15 years)' },
  { value: 'experienced', label: 'Experienced (15+ years)' },
  { value: 'transitioning', label: 'Transitioning from employed position' },
];

const US_STATES = [
  'AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID','IL','IN','IA',
  'KS','KY','LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ',
  'NM','NY','NC','ND','OH','OK','OR','PA','RI','SC','SD','TN','TX','UT','VT',
  'VA','WA','WV','WI','WY','DC',
].map((s) => ({ value: s, label: s }));

interface AssessmentFormProps {
  onComplete: () => void;
}

export default function AssessmentForm({ onComplete }: AssessmentFormProps) {
  const store = usePracticeStore();

  const {
    register,
    handleSubmit,
    setValue,
    formState: { errors },
  } = useForm<AssessmentFormData>({
    resolver: zodResolver(assessmentSchema),
    defaultValues: {
      physicianName: store.physicianName,
      targetState: store.targetState,
      targetCity: store.targetCity,
      specialty: store.specialty,
      practiceType: store.practiceType,
      timeline: store.timeline,
      budget: store.budget,
      experienceLevel: store.experienceLevel,
    },
  });

  const onSubmit = (data: AssessmentFormData) => {
    store.setFields(data);
    store.completeStep('assessment');
    onComplete();
  };

  const fillElyExample = () => {
    const example = {
      physicianName: 'Dr. Sarah Chen',
      targetState: 'MN',
      targetCity: 'Ely',
      specialty: 'family-medicine',
      practiceType: 'solo',
      timeline: '6-months',
      budget: '100k-250k',
      experienceLevel: 'mid-career',
    };
    Object.entries(example).forEach(([key, value]) => {
      setValue(key as keyof AssessmentFormData, value, { shouldValidate: true });
    });
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-8">
      <div>
        <h2 className="text-2xl font-bold text-neutral-900">Practice Assessment</h2>
        <p className="text-neutral-500 mt-1">
          Tell us about your goals and we will build a customized roadmap for your practice.
        </p>
      </div>

      {/* Ely scenario suggestion */}
      <Card className="border-primary-200 bg-primary-50/50">
        <CardContent className="flex items-start gap-3 py-3">
          <Lightbulb className="w-5 h-5 text-primary-600 flex-shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-primary-800">
              Try our example scenario
            </p>
            <p className="text-sm text-primary-600 mt-0.5">
              Dr. Sarah Chen opening a solo family medicine practice in Ely, MN -- a rural
              community with limited healthcare access.
            </p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="mt-2"
              onClick={fillElyExample}
            >
              <MapPin className="w-3.5 h-3.5" />
              Load Ely, MN Example
            </Button>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="md:col-span-2">
          <Input
            label="Physician Name"
            placeholder="Dr. Jane Smith"
            error={errors.physicianName?.message}
            {...register('physicianName')}
          />
        </div>

        <Select
          label="State"
          placeholder="Select a state"
          options={US_STATES}
          error={errors.targetState?.message}
          {...register('targetState')}
        />

        <Input
          label="City"
          placeholder="e.g., Ely"
          error={errors.targetCity?.message}
          {...register('targetCity')}
        />

        <Select
          label="Specialty"
          placeholder="Choose your specialty"
          options={SPECIALTIES}
          error={errors.specialty?.message}
          {...register('specialty')}
        />

        <Select
          label="Practice Type"
          placeholder="Choose practice model"
          options={PRACTICE_TYPES}
          error={errors.practiceType?.message}
          {...register('practiceType')}
        />

        <Select
          label="Target Timeline"
          placeholder="When do you want to open?"
          options={TIMELINES}
          error={errors.timeline?.message}
          {...register('timeline')}
        />

        <Select
          label="Startup Budget"
          placeholder="Estimated budget range"
          options={BUDGETS}
          error={errors.budget?.message}
          {...register('budget')}
        />

        <div className="md:col-span-2">
          <Select
            label="Experience Level"
            placeholder="Where are you in your career?"
            options={EXPERIENCE_LEVELS}
            error={errors.experienceLevel?.message}
            {...register('experienceLevel')}
          />
        </div>
      </div>

      <div className="flex justify-end pt-4">
        <Button type="submit" size="lg">
          Continue to Credentialing
        </Button>
      </div>
    </form>
  );
}
