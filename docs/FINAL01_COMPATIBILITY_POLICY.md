# FINAL-01 compatibility policy — RC5.3 candidate

RC5.2 can omit visible shapes stored in `mc:AlternateContent` from python-pptx's
shape iteration. An independent real Linux API reproduction confirmed that an
ordinary unsupported rectangle yields REVIEW_REQUIRED, while an equivalent
Choice/Fallback-wrapped rectangle incorrectly yields VERIFIED. XML preservation
and equal source/output rendered text do not establish complete visual inventory.

This candidate refuses every namespace-qualified `mc:AlternateContent` element
anywhere in slide, slide-layout or slide-master XML at upload intake. It examines
the existing bounded XML trees, independently of python-pptx shape iteration.
No branch is selected, expanded, flattened or edited. Existing package, XML,
depth, element-count, font-scaling and verification limits remain unchanged.
Layout/master parts are identified by their declared OPC content types as well
as conventional paths, so relocating a valid part does not bypass refusal.
Such parts share the existing aggregate referenced-XML inspection budget.

This is a deliberately narrower compatibility policy: legitimate presentations
containing even empty or metadata-only compatibility wrappers in these parts are
refused. Hidden slides, suppressed inheritance and unused layouts/masters do not
exempt them. The policy does not infer visibility from branch contents. It does
not reject a same-named element in another namespace, nor change theme handling.
Users must supply a presentation without this unsupported markup; the application
does not automatically normalize it. The original upload is never rewritten.

The original RC5.2 qualified archive and its historical qualification remain
unchanged. This candidate has a different source fingerprint and must pass its
own complete Linux qualification and fresh-export checks before release. A
configured runtime release label is not its source identity.
