"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { useAuth } from "@/components/auth-provider";
import { login, toUiError } from "@/services/api";
import type { ApiError } from "@/types/api";

export default function LoginPage() {
  const router = useRouter();
  const { setSession } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      const tokens = await login({ email, password });
      await setSession(tokens);
      router.replace("/app");
    } catch (nextError) {
      setError(toUiError(nextError));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="authPage">
      <form className="authPanel" onSubmit={handleSubmit}>
        <div>
          <strong className="brand">Notas de Devolucao</strong>
          <h1>Entrar</h1>
          <p>Acesse a operacao de devolucoes, notas e emissoes mockadas.</p>
        </div>

        {error ? <div className="errorBox">{error.message}</div> : null}

        <label>
          Email
          <input
            autoComplete="email"
            onChange={(event) => setEmail(event.target.value)}
            required
            type="email"
            value={email}
          />
        </label>
        <label>
          Senha
          <input
            autoComplete="current-password"
            onChange={(event) => setPassword(event.target.value)}
            required
            type="password"
            value={password}
          />
        </label>

        <button disabled={isSubmitting} type="submit">
          {isSubmitting ? "Entrando..." : "Entrar"}
        </button>
        <Link className="textLink" href="/register">
          Criar conta
        </Link>
      </form>
    </main>
  );
}
