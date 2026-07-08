import type {
  FieldErrors,
  FieldValues,
  Resolver,
  ResolverResult,
} from "react-hook-form";
import type { ZodType } from "zod";

/**
 * Minimal Zod resolver for react-hook-form. Kept local to avoid adding the
 * `@hookform/resolvers` dependency for the small set of flat auth forms we use.
 * Maps each Zod issue to a single field error keyed by its (dot-joined) path.
 */
export function zodResolver<T extends FieldValues>(
  schema: ZodType<T>,
): Resolver<T> {
  return async (values): Promise<ResolverResult<T>> => {
    const result = schema.safeParse(values);
    if (result.success) {
      return { values: result.data, errors: {} };
    }

    const errors: Record<string, { type: string; message: string }> = {};
    for (const issue of result.error.issues) {
      const path = issue.path.join(".");
      // First issue per field wins (matches RHF default behavior).
      if (path && !errors[path]) {
        errors[path] = { type: issue.code, message: issue.message };
      }
    }

    return {
      values: {},
      errors: errors as FieldErrors<T>,
    };
  };
}
