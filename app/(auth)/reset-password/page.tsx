import { Suspense } from "react";
import { AuthFrame } from "@/components/auth-frame";
import { ResetForm } from "./reset-form";

export default function ResetPasswordPage() {
  return (
    <AuthFrame>
      <Suspense>
        <ResetForm />
      </Suspense>
    </AuthFrame>
  );
}
