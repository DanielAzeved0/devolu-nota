"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { getCurrentUser, listCompanies } from "@/services/api";
import type { AuthTokens, CompanyPublic, UserPublic } from "@/types/api";

type AuthContextValue = {
  accessToken: string | null;
  refreshToken: string | null;
  user: UserPublic | null;
  companies: CompanyPublic[];
  activeCompanyId: string | null;
  activeCompany: CompanyPublic | null;
  isBootstrapping: boolean;
  setSession: (tokens: AuthTokens) => Promise<void>;
  logout: () => void;
  refreshCompanies: () => Promise<void>;
  selectCompany: (companyId: string) => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

const accessTokenKey = "devolu.accessToken";
const refreshTokenKey = "devolu.refreshToken";
const activeCompanyKey = "devolu.activeCompanyId";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState<string | null>(null);
  const [user, setUser] = useState<UserPublic | null>(null);
  const [companies, setCompanies] = useState<CompanyPublic[]>([]);
  const [activeCompanyId, setActiveCompanyId] = useState<string | null>(null);
  const [isBootstrapping, setIsBootstrapping] = useState(true);

  const clearSession = useCallback(() => {
    localStorage.removeItem(accessTokenKey);
    localStorage.removeItem(refreshTokenKey);
    localStorage.removeItem(activeCompanyKey);
    setAccessToken(null);
    setRefreshToken(null);
    setUser(null);
    setCompanies([]);
    setActiveCompanyId(null);
  }, []);

  const loadCompanies = useCallback(async (token: string) => {
    const nextCompanies = await listCompanies(token);
    setCompanies(nextCompanies);
    const storedCompanyId = localStorage.getItem(activeCompanyKey);
    const nextActiveCompanyId =
      nextCompanies.find((company) => company.id === storedCompanyId)?.id ?? nextCompanies[0]?.id ?? null;
    setActiveCompanyId(nextActiveCompanyId);
    if (nextActiveCompanyId) {
      localStorage.setItem(activeCompanyKey, nextActiveCompanyId);
    }
  }, []);

  useEffect(() => {
    const bootstrap = async () => {
      const storedAccessToken = localStorage.getItem(accessTokenKey);
      const storedRefreshToken = localStorage.getItem(refreshTokenKey);
      if (!storedAccessToken) {
        setIsBootstrapping(false);
        return;
      }

      try {
        const [currentUser] = await Promise.all([
          getCurrentUser(storedAccessToken),
          loadCompanies(storedAccessToken)
        ]);
        setAccessToken(storedAccessToken);
        setRefreshToken(storedRefreshToken);
        setUser(currentUser);
      } catch {
        clearSession();
      } finally {
        setIsBootstrapping(false);
      }
    };

    void bootstrap();
  }, [clearSession, loadCompanies]);

  const setSession = useCallback(
    async (tokens: AuthTokens) => {
      localStorage.setItem(accessTokenKey, tokens.access_token);
      localStorage.setItem(refreshTokenKey, tokens.refresh_token);
      setAccessToken(tokens.access_token);
      setRefreshToken(tokens.refresh_token);
      const [currentUser] = await Promise.all([
        getCurrentUser(tokens.access_token),
        loadCompanies(tokens.access_token)
      ]);
      setUser(currentUser);
    },
    [loadCompanies]
  );

  const refreshCompanies = useCallback(async () => {
    if (!accessToken) {
      return;
    }
    await loadCompanies(accessToken);
  }, [accessToken, loadCompanies]);

  const selectCompany = useCallback((companyId: string) => {
    setActiveCompanyId(companyId);
    localStorage.setItem(activeCompanyKey, companyId);
  }, []);

  const activeCompany = useMemo(
    () => companies.find((company) => company.id === activeCompanyId) ?? null,
    [activeCompanyId, companies]
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      accessToken,
      refreshToken,
      user,
      companies,
      activeCompanyId,
      activeCompany,
      isBootstrapping,
      setSession,
      logout: clearSession,
      refreshCompanies,
      selectCompany
    }),
    [
      accessToken,
      activeCompany,
      activeCompanyId,
      clearSession,
      companies,
      isBootstrapping,
      refreshCompanies,
      refreshToken,
      selectCompany,
      setSession,
      user
    ]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return context;
}
