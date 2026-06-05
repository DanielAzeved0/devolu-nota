"use client";

import { useEffect, useState } from "react";
import { getApiHealth } from "@/services/api";

type HealthStatus = "loading" | "online" | "offline";

export function ApiHealthBadge() {
  const [status, setStatus] = useState<HealthStatus>("loading");

  useEffect(() => {
    let isMounted = true;

    getApiHealth().then((health) => {
      if (isMounted) {
        setStatus(health.ok ? "online" : "offline");
      }
    });

    return () => {
      isMounted = false;
    };
  }, []);

  if (status === "loading") {
    return <span className="health">Verificando API...</span>;
  }

  if (status === "offline") {
    return <span className="health error">API indisponivel</span>;
  }

  return <span className="health ok">API online</span>;
}
