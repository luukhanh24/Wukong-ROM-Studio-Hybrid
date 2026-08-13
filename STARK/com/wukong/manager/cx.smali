.class public final Lcom/wukong/manager/cx;
.super Ljava/lang/Object;
.source "SourceFile"


# instance fields
.field public final e:Ljava/lang/String;

.field public final f:Ljava/io/Serializable;


# direct methods
.method public constructor <init>(Ljava/lang/Class;Ljava/lang/String;)V
    .registers 3

    .line 422
    invoke-direct {p0}, Ljava/lang/Object;-><init>()V

    .line 423
    iput-object p1, p0, Lcom/wukong/manager/cx;->f:Ljava/io/Serializable;

    .line 424
    iput-object p2, p0, Lcom/wukong/manager/cx;->e:Ljava/lang/String;

    return-void
.end method

.method public constructor <init>(Ljava/lang/String;Ljava/lang/String;)V
    .registers 3

    .line 987
    invoke-direct {p0}, Ljava/lang/Object;-><init>()V

    .line 988
    iput-object p1, p0, Lcom/wukong/manager/cx;->e:Ljava/lang/String;

    .line 989
    iput-object p2, p0, Lcom/wukong/manager/cx;->f:Ljava/io/Serializable;

    return-void
.end method
