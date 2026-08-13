.class public abstract synthetic Lcom/wukong/manager/ct;
.super Ljava/lang/Object;
.source "SourceFile"


# direct methods
.method public static synthetic e(I)Landroid/content/AttributionSource$Builder;
    .registers 2

    new-instance v0, Landroid/content/AttributionSource$Builder;

    invoke-direct {v0, p0}, Landroid/content/AttributionSource$Builder;-><init>(I)V

    return-object v0
.end method

.method public static bridge synthetic f(Landroid/content/AttributionSource$Builder;Ljava/lang/String;)Landroid/content/AttributionSource$Builder;
    .registers 2

    invoke-virtual {p0, p1}, Landroid/content/AttributionSource$Builder;->setPackageName(Ljava/lang/String;)Landroid/content/AttributionSource$Builder;

    move-result-object p0

    return-object p0
.end method

.method public static bridge synthetic g(Landroid/content/AttributionSource$Builder;)Landroid/content/AttributionSource;
    .registers 1

    invoke-virtual {p0}, Landroid/content/AttributionSource$Builder;->build()Landroid/content/AttributionSource;

    move-result-object p0

    return-object p0
.end method

.method public static bridge synthetic h()Ljava/lang/Class;
    .registers 1

    const-class v0, Landroid/content/AttributionSource;

    return-object v0
.end method

.method public static synthetic i()V
    .registers 1

    new-instance v0, Landroid/content/AttributionSource$Builder;

    return-void
.end method
