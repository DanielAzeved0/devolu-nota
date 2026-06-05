import { getApiHealth } from "@/services/api";

export async function ApiHealthBadge() {
  const health = await getApiHealth();

  if (!health.ok) {
    return <span className="health error">API indisponivel</span>;
  }

  return <span className="health ok">API online</span>;
}

