import { create } from 'zustand';

export interface PracticeState {
  // Assessment
  physicianName: string;
  specialty: string;
  targetState: string;
  targetCity: string;
  practiceType: string;
  timeline: string;
  budget: string;
  experienceLevel: string;

  // Progress tracking
  currentStep: number;
  stepsCompleted: Record<string, boolean>;

  // Credentials
  npiNumber: string;
  deaNumber: string;
  stateLicense: string;
  boardCertification: string;
  malpracticeInsurance: string;

  // Business
  entityType: string;
  ein: string;
  practiceName: string;
  businessAddress: string;

  // Compliance
  cmsEnrolled: boolean;
  hipaaCompliant: boolean;
  oigClear: boolean;
  cliaRequired: boolean;
  cliaNumber: string;

  // Clinical
  ehrSystem: string;
  ePrescribing: boolean;
  labConnectivity: boolean;
  fhirEnabled: boolean;

  // Financial
  billingSystem: string;
  startupBudget: string;
  feeScheduleSet: boolean;
  payerContracts: string[];

  // Network
  directoryListings: string[];
  referralPartners: string[];

  // Actions
  setField: <K extends keyof PracticeState>(field: K, value: PracticeState[K]) => void;
  setFields: (fields: Partial<PracticeState>) => void;
  nextStep: () => void;
  prevStep: () => void;
  goToStep: (step: number) => void;
  completeStep: (step: string) => void;
  reset: () => void;
}

const TOTAL_STEPS = 7;

const initialState = {
  physicianName: '',
  specialty: '',
  targetState: '',
  targetCity: '',
  practiceType: '',
  timeline: '',
  budget: '',
  experienceLevel: '',
  currentStep: 0,
  stepsCompleted: {} as Record<string, boolean>,
  npiNumber: '',
  deaNumber: '',
  stateLicense: '',
  boardCertification: '',
  malpracticeInsurance: '',
  entityType: '',
  ein: '',
  practiceName: '',
  businessAddress: '',
  cmsEnrolled: false,
  hipaaCompliant: false,
  oigClear: false,
  cliaRequired: false,
  cliaNumber: '',
  ehrSystem: '',
  ePrescribing: false,
  labConnectivity: false,
  fhirEnabled: false,
  billingSystem: '',
  startupBudget: '',
  feeScheduleSet: false,
  payerContracts: [] as string[],
  directoryListings: [] as string[],
  referralPartners: [] as string[],
};

export const usePracticeStore = create<PracticeState>((set) => ({
  ...initialState,

  setField: (field, value) =>
    set((state) => ({ ...state, [field]: value })),

  setFields: (fields) =>
    set((state) => ({ ...state, ...fields })),

  nextStep: () =>
    set((state) => ({
      currentStep: Math.min(state.currentStep + 1, TOTAL_STEPS - 1),
    })),

  prevStep: () =>
    set((state) => ({
      currentStep: Math.max(state.currentStep - 1, 0),
    })),

  goToStep: (step: number) =>
    set(() => ({
      currentStep: Math.max(0, Math.min(step, TOTAL_STEPS - 1)),
    })),

  completeStep: (step: string) =>
    set((state) => ({
      stepsCompleted: { ...state.stepsCompleted, [step]: true },
    })),

  reset: () => set(() => ({ ...initialState, stepsCompleted: {} })),
}));

export const ONBOARDING_STEPS = [
  { id: 'assessment', label: 'Assessment', description: 'Tell us about your practice goals' },
  { id: 'credentialing', label: 'Credentialing', description: 'Verify licenses and certifications' },
  { id: 'formation', label: 'Business Formation', description: 'Establish your legal entity' },
  { id: 'compliance', label: 'Regulatory Compliance', description: 'CMS, HIPAA, OIG, and CLIA' },
  { id: 'clinical', label: 'Clinical Setup', description: 'EHR, e-prescribing, and lab connections' },
  { id: 'financial', label: 'Financial Setup', description: 'Billing, budgets, and payer contracts' },
  { id: 'launch', label: 'Launch', description: 'Directory listings and go-live readiness' },
] as const;
