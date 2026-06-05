"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { useAuth } from "@/components/auth-provider";
import { register, toUiError } from "@/services/api";
import type { ApiError } from "@/types/api";

export default function RegisterPage() {
  const router = useRouter();
  const { setSession } = useAuth();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      const tokens = await register({ name, email, password });
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
          <h1>Criar conta</h1>
          <p>Cadastre o primeiro usuario para operar o MVP.</p>
        </div>

        {error ? <div className="errorBox">{error.message}</div> : null}

        <label>
          Nome
          <input onChange={(event) => setName(event.target.value)} required type="text" value={name} />
        </label>
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
            autoComplete="new-password"
            onChange={(event) => setPassword(event.target.value)}
            required
            type="password"
            value={password}
          />
        </label>

        <button disabled={isSubmitting} type="submit">
          {isSubmitting ? "Criando..." : "Criar conta"}
        </button>
        <Link className="textLink" href="/login">
          Ja tenho conta
        </Link>
      </form>
    </main>
  );
}
