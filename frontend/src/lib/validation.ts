// minLength=0 means no validation required
export function validatePassword(pw: string, minLength = 8): string {
  if (minLength === 0) return "";
  if (pw.length < minLength) return `At least ${minLength} characters required`;
  if (!/[A-Za-z]/.test(pw)) return "Must contain at least one letter";
  if (!/[0-9]/.test(pw)) return "Must contain at least one digit";
  return "";
}
