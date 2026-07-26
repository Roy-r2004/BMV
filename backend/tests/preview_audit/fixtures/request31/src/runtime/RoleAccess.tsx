import type { ReactNode } from "react";

type Props = {
  pageId: string;
  roleIds: readonly string[];
  children: ReactNode;
};

export function RoleAccess({ pageId, roleIds, children }: Props) {
  return (
    <div
      data-bmv-route-page-id={pageId}
      data-bmv-role-ids={roleIds.join(",")}
    >
      {children}
    </div>
  );
}
