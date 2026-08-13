.class public final Lcom/wukong/manager/cv;
.super Ljava/lang/Object;
.source "SourceFile"


# instance fields
.field public final e:I

.field public final f:[Ljava/lang/String;

.field public final g:[Ljava/lang/String;


# direct methods
.method public constructor <init>(I[Ljava/lang/String;[Ljava/lang/String;)V
    .registers 4

    .line 951
    invoke-direct {p0}, Ljava/lang/Object;-><init>()V

    and-int/lit8 p1, p1, 0xf

    .line 952
    iput p1, p0, Lcom/wukong/manager/cv;->e:I

    const/4 p1, 0x0

    if-eqz p2, :cond_b

    goto :goto_d

    .line 958
    :cond_b
    new-array p2, p1, [Ljava/lang/String;

    :goto_d
    iput-object p2, p0, Lcom/wukong/manager/cv;->f:[Ljava/lang/String;

    if-eqz p3, :cond_12

    goto :goto_14

    .line 959
    :cond_12
    new-array p3, p1, [Ljava/lang/String;

    :goto_14
    iput-object p3, p0, Lcom/wukong/manager/cv;->g:[Ljava/lang/String;

    return-void
.end method
