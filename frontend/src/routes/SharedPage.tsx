/**
 * A package someone shared: read-only, through a link its owner made.
 *
 * The partner sees what the owner sees on their plans page — the answer, the
 * documents, the roadmap, the calls made so far and the screens — and can
 * download all of it. They cannot make a call, give the go-ahead, or make a
 * link of their own; the owner's page keeps those.
 */
import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import {
  consultantAssetUrl,
  downloadSharedExport,
  getSharedPackage,
  isForbidden,
  type SharedPackage,
} from '../api/consultant';
import Chrome from '../components/consult/Chrome';
import Package, { type PackageScreen } from '../components/consult/Package';
import '../styles/consult.css';

export default function SharedPage() {
  const { token = '' } = useParams<{ token: string }>();
  const [data, setData] = useState<SharedPackage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [zoom, setZoom] = useState<PackageScreen | null>(null);

  useEffect(() => {
    let cancelled = false;
    getSharedPackage(token)
      .then((d) => !cancelled && setData(d))
      .catch((err) => {
        if (cancelled) return;
        setError(
          isForbidden(err)
            ? 'This package is still being reviewed. The link will open once it is released.'
            : "This link doesn't open anything. It may have been turned off by the person who shared it.",
        );
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  const screens: PackageScreen[] = (data?.screens ?? [])
    .map((s) => ({
      label: s.role_label,
      src: consultantAssetUrl(s.hero_url ?? s.image_url) ?? '',
      full: consultantAssetUrl(s.image_url) ?? '',
    }))
    .filter((s) => s.src);

  return (
    <div className="cx">
      <Chrome step={5} where="Shared with you" />
      <main className="cx-wrap">
        {error ? (
          <section className="max-w-[640px] pt-[10vh]">
            <h1 className="cx-h2">Nothing to show here.</h1>
            <p className="cx-lead mt-5">{error}</p>
            <Link to="/demo" className="cx-btn cx-btn--blue mt-10">Start your own consultation</Link>
          </section>
        ) : !data ? (
          <p className="cx-lead pt-[10vh]">Opening the package<span className="cx-typing"><i /><i /><i /></span></p>
        ) : (
          <>
            <p className="cx-faint pt-6 text-[15px]">Shared with you, read-only. Prepared by Build My Version for {data.business_name}.</p>
            <Package
              businessName={data.business_name}
              answer={data.answer}
              fallbackFinding={data.summary}
              roadmap={data.action_plan}
              decisions={data.decisions ?? {}}
              unverified={data.unverified}
              screens={screens}
              docs={data.documents}
              onDownload={(k) => downloadSharedExport(token, k)}
              readOnly
              onOpenScreen={setZoom}
            />
          </>
        )}
      </main>
      {zoom ? (
        <div className="cx-modal-back" role="dialog" aria-modal="true" aria-label={zoom.label} onClick={() => setZoom(null)}>
          <img src={zoom.full} alt={zoom.label} className="max-h-[90vh] max-w-[94vw] rounded-2xl shadow-2xl" />
        </div>
      ) : null}
    </div>
  );
}
