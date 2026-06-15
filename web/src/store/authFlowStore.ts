import { create } from 'zustand';

// Carries the email between the multi-step auth screens (signup email -> password,
// login email -> password), replacing the Flutter signup/login email providers.
interface AuthFlowState {
  email: string;
  setEmail: (email: string) => void;
}

export const useAuthFlowStore = create<AuthFlowState>((set) => ({
  email: '',
  setEmail: (email) => set({ email }),
}));
