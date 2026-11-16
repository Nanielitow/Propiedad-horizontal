"use client";

import { createContext, useContext } from "react";

import type { Membership, User } from "@/lib/types";

interface TenantContextValue {
  user: User;
  memberships: Membership[];
  tenant: Membership;
  isAdmin: boolean;
}

const TenantContext = createContext<TenantContextValue | null>(null);

export function TenantProvider({ value, children }: { value: TenantContextValue; children: React.ReactNode }) {
  return <TenantContext.Provider value={value}>{children}</TenantContext.Provider>;
}

export function useTenant(): TenantContextValue {
  const ctx = useContext(TenantContext);
  if (!ctx) throw new Error("useTenant debe usarse dentro de TenantProvider");
  return ctx;
}
