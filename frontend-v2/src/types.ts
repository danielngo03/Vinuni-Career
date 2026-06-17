export type Role = "student" | "company" | "admin";

export type Skill = {
  name: string;
  score: number;
  confidence: number;
  evidence: string;
};

export type Experience = {
  title: string;
  company: string;
  duration: string;
  score: number;
  summary: string;
};

export type Education = {
  degree: string;
  institution: string;
  year: string;
  score: number;
};

export type Student = {
  id: string;
  name: string;
  target: string;
  email: string;
  phone: string;
  location: string;
  university: string;
  major: string;
  graduationYear: string;
  bio: string;
  skills: Skill[];
  experiences: Experience[];
  education: Education[];
};

export type Job = {
  id: string;
  companyId: string;
  companyName: string;
  title: string;
  status: "open" | "closed";
  location: string;
  employmentType: string;
  requiredSkills: string[];
  optionalSkills: string[];
  salary: string;
  experienceRequirements?: {
    required: boolean;
    min_months: number;
    preferred_titles: string[];
    keywords: string[];
    importance: number;
  };
  educationRequirements?: {
    required: boolean;
    degrees: string[];
    fields_of_study: string[];
    certifications: string[];
    keywords: string[];
    importance: number;
  };
};

export type MatchingWeights = {
  skill_weight: number;
  experience_weight: number;
  education_weight: number;
};

export type Match = {
  id: string;
  title: string;
  subtitle: string;
  score: number;
  decision: "Shortlist" | "Review" | "Gap";
  strengths: string[];
  gaps: string[];
};
