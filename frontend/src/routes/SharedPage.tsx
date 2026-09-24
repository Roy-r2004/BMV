/**
 * A package someone shared: read-only, through a link its owner made.
 *
 * The partner sees what the owner sees on their package page — the answer,
 * Monday's steps, the documents, the screens and the pilot so far — and can
 * download all of it. They cannot answer anything, log a week, or make a link
 * of their own; the owner's page keeps those.
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

  const built = Boolean(data?.documents.blueprint || data?.documents.technical);

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
              mode={built ? 'full' : 'plan'}
              businessName={data.business_name}
              answer={data.answer}
              fallbackFinding={data.summary}
              capacity={data.capacity}
              plan={data.action_plan}
              log={data.pilot_log}
              unverified={data.unverified}
              screens={screens}
              docs={data.documents}
              onDownload={(k) => downloadSharedExport(token, k)}
              canEdit={false}
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
